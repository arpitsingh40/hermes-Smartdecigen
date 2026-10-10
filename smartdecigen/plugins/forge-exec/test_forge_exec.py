"""Tests for forge-exec — the execution layer.

The properties that matter, and why each is asserted:
  * dry-run by default — a side-effecting tool must not fire unless explicitly enabled
  * idempotency        — a re-fired cron must not duplicate an action
  * kernel gating      — money actions ask first, and fail CLOSED
  * audit              — every action leaves a ledger line, including blocks

Run:  python -m pytest test_forge_exec.py -v
"""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fx  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_DIR", str(tmp_path))
    for v in ("FORGE_EXEC_LIVE", "FORGE_EXEC_FAIL_OPEN", "FORGE_EXEC_JWT",
              "FORGE_EXEC_ORG_ID", "FORGE_EXEC_KERNEL_URL"):
        monkeypatch.delenv(v, raising=False)
    yield tmp_path


def _lines(tmp_path, name):
    p = tmp_path / f"{name}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# --------------------------------------------------------------------------- ledger basics

def test_log_action_writes_a_line(tmp_path):
    out = json.loads(fx.forge_log_action(action="follow_up_lead", target="lead-1", detail="called"))
    assert out["success"] is True
    rows = _lines(tmp_path, "actions")
    assert len(rows) == 1 and rows[0]["action"] == "follow_up_lead"
    assert rows[0]["dedupe_key"]


def test_record_metric_appends(tmp_path):
    fx.forge_record_metric(name="revenue", value=1000)
    fx.forge_record_metric(name="revenue", value=1200)
    rows = _lines(tmp_path, "metrics")
    assert [r["value"] for r in rows] == [1000, 1200]


def test_ledger_dir_created_lazily(tmp_path):
    assert not (tmp_path / "actions.jsonl").exists()
    fx.forge_log_action(action="x")
    assert (tmp_path / "actions.jsonl").exists()


# --------------------------------------------------------------------------- queue idempotency

def test_queue_action_enqueues(tmp_path):
    out = json.loads(fx.forge_queue_action(action="send_campaign", target="list-a", detail="diwali"))
    assert out["queued"] is True
    assert len(_lines(tmp_path, "queue")) == 1


def test_queue_action_is_idempotent_on_derived_key(tmp_path):
    a = json.loads(fx.forge_queue_action(action="send_campaign", target="list-a", detail="diwali"))
    b = json.loads(fx.forge_queue_action(action="send_campaign", target="list-a", detail="diwali"))
    assert a["queued"] is True
    assert b["queued"] is False and b["reason"] == "already queued"
    assert len(_lines(tmp_path, "queue")) == 1, "a repeat must not duplicate the entry"


def test_queue_action_is_idempotent_on_explicit_key(tmp_path):
    fx.forge_queue_action(action="a", target="t", detail="d", dedupe_key="K1")
    out = json.loads(fx.forge_queue_action(action="different", target="x", detail="y", dedupe_key="K1"))
    assert out["queued"] is False


def test_list_queue_filters_by_status(tmp_path):
    fx.forge_queue_action(action="a", dedupe_key="K1")
    fx.forge_queue_action(action="b", dedupe_key="K2")
    assert json.loads(fx.forge_list_queue(status="pending"))["count"] == 2
    assert json.loads(fx.forge_list_queue(status="done"))["count"] == 0
    assert json.loads(fx.forge_list_queue(status="all"))["count"] == 2


# --------------------------------------------------------------------------- kernel gate

def test_ungated_action_skips_the_kernel(monkeypatch):
    """A non-money action must not require kernel credentials."""
    out = json.loads(fx.forge_log_action(action="internal_note"))
    assert out["success"] is True


def test_money_action_blocked_without_credentials(monkeypatch):
    """No JWT/org configured and not fail-open -> refuse. This is the fail-closed default."""
    out = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="hello there"))
    assert out["success"] is False
    assert out["blocked"] is True
    assert "credentials not configured" in out["reason"]


def test_money_action_fail_open_when_opted_in(monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    out = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="hello there"))
    # fail-open allows it through the gate; dry-run still prevents the actual send
    assert out["success"] is True
    assert out["sent"] is False and out["dry_run"] is True


def test_gate_respects_a_kernel_block(monkeypatch):
    """A kernel 'blocked' verdict must refuse the action."""
    monkeypatch.setenv("FORGE_EXEC_JWT", "tok")
    monkeypatch.setenv("FORGE_EXEC_ORG_ID", "org")
    monkeypatch.setattr(fx, "_kernel_gate",
                        lambda *a, **k: {"allowed": False, "verdict": "blocked",
                                         "reason": "Weekly spend cap exceeded: $10.00 / $10.00"})
    out = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="hello there"))
    assert out["blocked"] is True and "cap exceeded" in out["reason"]


def test_blocked_action_is_still_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_JWT", "tok")
    monkeypatch.setenv("FORGE_EXEC_ORG_ID", "org")
    monkeypatch.setattr(fx, "_kernel_gate",
                        lambda *a, **k: {"allowed": False, "verdict": "blocked", "reason": "cap"})
    fx.forge_send_message(channel="email", to="a@b.c", body="hello there")
    rows = _lines(tmp_path, "actions")
    assert len(rows) == 1 and rows[0]["outcome"] == "blocked"


# --------------------------------------------------------------------------- dry-run default

def test_send_is_dry_run_by_default(monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    out = json.loads(fx.forge_send_message(channel="whatsapp", to="+91999", body="hi there"))
    assert out["dry_run"] is True
    assert out["sent"] is False
    assert "FORGE_EXEC_LIVE is not set" in out["note"]


def test_send_records_the_would_have(monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    out = json.loads(fx.forge_send_message(channel="email", to="x@y.z", body="body text"))
    assert "send email message to x@y.z" in out["would_have"]


def test_send_does_not_claim_success_when_unconfigured(monkeypatch):
    """With LIVE set but no transport, the tool must NOT report sent=True. Faking success is
    the worst possible failure mode for an execution layer."""
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    monkeypatch.setenv("FORGE_EXEC_LIVE", "1")
    out = json.loads(fx.forge_send_message(channel="email", to="x@y.z", body="body text"))
    assert out["sent"] is False
    assert "no transport is configured" in out["note"]


# --------------------------------------------------------------------------- idempotent send

def test_send_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    a = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="same body"))
    b = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="same body"))
    assert a["dry_run"] is True
    assert b["sent"] is False and "already sent" in b["reason"]
    assert len(_lines(tmp_path, "actions")) == 1


def test_send_explicit_key_prevents_duplicate(monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    fx.forge_send_message(channel="email", to="a@b.c", body="one", dedupe_key="lead-1-day1")
    out = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="two",
                                           dedupe_key="lead-1-day1"))
    assert out["sent"] is False and "already sent" in out["reason"]


def test_different_body_is_a_different_action(monkeypatch):
    monkeypatch.setenv("FORGE_EXEC_FAIL_OPEN", "1")
    a = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="first"))
    b = json.loads(fx.forge_send_message(channel="email", to="a@b.c", body="second"))
    assert a["dry_run"] is True and b["dry_run"] is True


# --------------------------------------------------------------------------- registration

class _Ctx:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description="", **kw):
        self.tools.append((name, toolset, schema, handler))


def test_registers_the_five_tools():
    ctx = _Ctx()
    fx.register(ctx)
    names = {t[0] for t in ctx.tools}
    assert names == {"forge_log_action", "forge_queue_action", "forge_list_queue",
                     "forge_record_metric", "forge_send_message"}


def test_all_tools_share_one_toolset():
    ctx = _Ctx()
    fx.register(ctx)
    assert {t[1] for t in ctx.tools} == {"forge_exec"}


def test_every_tool_has_a_schema():
    ctx = _Ctx()
    fx.register(ctx)
    for name, _, schema, _ in ctx.tools:
        assert schema["name"] == name
        assert schema.get("description")
        assert "parameters" in schema


def test_registered_handler_is_callable_with_args(monkeypatch):
    ctx = _Ctx()
    fx.register(ctx)
    handler = next(h for n, _, _, h in ctx.tools if n == "forge_log_action")
    out = json.loads(handler({"action": "test", "target": "t"}, task_id="task-1"))
    assert out["success"] is True
