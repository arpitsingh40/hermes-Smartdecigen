"""Tests for forge-loop — the autonomous loop's state helpers.

Run:  python -m pytest test_forge_loop.py -v
"""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fl  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_LOOP_DIR", str(tmp_path))
    monkeypatch.delenv("FORGE_LOOP_MAX_ACT", raising=False)
    yield tmp_path


def _state():
    return json.loads(fl.forge_loop_state())


# --------------------------------------------------------------------------- empty state

def test_state_on_a_fresh_install(tmp_path):
    s = _state()
    assert s["queue"]["pending"] == 0
    assert s["recent_actions"] == []
    assert s["metrics"] == {}
    assert s["last_runs"] == []
    assert s["budget"]["max_actions_per_iteration"] == 3
    assert str(tmp_path) == s["state_dir"]


def test_budget_is_configurable(monkeypatch):
    monkeypatch.setenv("FORGE_LOOP_MAX_ACT", "1")
    assert _state()["budget"]["max_actions_per_iteration"] == 1


def test_budget_floor(monkeypatch):
    """A budget of 0 or negative must clamp to 1 — the loop always gets to act once."""
    monkeypatch.setenv("FORGE_LOOP_MAX_ACT", "0")
    assert _state()["budget"]["max_actions_per_iteration"] == 1


# --------------------------------------------------------------------------- queue

def _write(tmp_path, name, rows):
    p = tmp_path / f"{name}.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_pending_queue_counted(tmp_path):
    _write(tmp_path, "queue", [
        {"dedupe_key": "a", "status": "pending", "action": "x"},
        {"dedupe_key": "b", "status": "done", "action": "y"},
        {"dedupe_key": "c", "status": "pending", "action": "z"},
    ])
    s = _state()
    assert s["queue"]["pending"] == 2
    assert {e["dedupe_key"] for e in s["queue"]["entries"]} == {"a", "c"}


def test_complete_action_flips_status(tmp_path):
    _write(tmp_path, "queue", [{"dedupe_key": "a", "status": "pending"}])
    out = json.loads(fl.forge_loop_complete_action(dedupe_key="a", outcome="done", note="sent"))
    assert out["success"] is True
    assert (tmp_path / "queue.jsonl").read_text().count("\n") == 2


def test_completed_action_leaves_the_pending_count(tmp_path):
    """The queue is append-only, so completion is a NEW line with the same key. The state reader
    must collapse to the latest line per key, or a finished action looks pending forever."""
    _write(tmp_path, "queue", [
        {"dedupe_key": "a", "status": "pending", "action": "follow_up"},
        {"dedupe_key": "b", "status": "pending", "action": "follow_up"},
    ])
    assert _state()["queue"]["pending"] == 2
    fl.forge_loop_complete_action(dedupe_key="a", outcome="done")
    s = _state()
    assert s["queue"]["pending"] == 1
    assert {e["dedupe_key"] for e in s["queue"]["entries"]} == {"b"}


def test_collapse_preserves_the_original_payload(tmp_path):
    """A completion line carries no action/target — merging must not erase them.

    Asserted on _resolve_queue directly: `state()['queue']['entries']` lists only PENDING items,
    and this entry is done, so it correctly does not appear there.
    """
    _write(tmp_path, "queue", [
        {"dedupe_key": "a", "status": "pending", "action": "send_campaign", "target": "list-a"},
        {"dedupe_key": "a", "status": "done", "note": "sent"},
    ])
    resolved = fl._resolve_queue(fl._read("queue"))
    assert len(resolved) == 1
    entry = resolved[0]
    assert entry["status"] == "done"
    assert entry["action"] == "send_campaign", "payload must survive the merge"
    assert entry["target"] == "list-a"
    assert entry["note"] == "sent"
    # and it is correctly absent from the pending list
    assert _state()["queue"]["pending"] == 0


def test_complete_unknown_key_is_refused(tmp_path):
    out = json.loads(fl.forge_loop_complete_action(dedupe_key="nope"))
    assert out["success"] is False and "no such dedupe_key" in out["reason"]


# --------------------------------------------------------------------------- metrics trend

def test_metric_trend_computes_delta(tmp_path):
    _write(tmp_path, "metrics", [
        {"metric": "revenue", "value": 1000},
        {"metric": "revenue", "value": 1250},
    ])
    m = _state()["metrics"]["revenue"]
    assert m["latest"] == 1250
    assert m["previous"] == 1000
    assert m["delta"] == 250
    assert m["n"] == 2


def test_single_metric_point_has_no_delta(tmp_path):
    _write(tmp_path, "metrics", [{"metric": "leads", "value": 5}])
    m = _state()["metrics"]["leads"]
    assert m["latest"] == 5 and m["delta"] is None


def test_metrics_are_tracked_separately(tmp_path):
    _write(tmp_path, "metrics", [
        {"metric": "revenue", "value": 100}, {"metric": "leads", "value": 3},
        {"metric": "revenue", "value": 150},
    ])
    s = _state()["metrics"]
    assert s["revenue"]["delta"] == 50
    assert s["leads"]["latest"] == 3


def test_non_numeric_metric_points_are_ignored(tmp_path):
    _write(tmp_path, "metrics", [
        {"metric": "x", "value": "not a number"}, {"metric": "x", "value": 10},
    ])
    m = _state()["metrics"]["x"]
    assert m["latest"] == 10


# --------------------------------------------------------------------------- actions + blocks

def test_blocked_actions_surface(tmp_path):
    _write(tmp_path, "actions", [
        {"action": "send_message", "outcome": "dry_run"},
        {"action": "send_message", "outcome": "blocked", "reason": "cap exceeded"},
    ])
    s = _state()
    assert len(s["blocked_actions"]) == 1
    assert "cap exceeded" in s["blocked_actions"][0]["reason"]


def test_recent_actions_are_returned(tmp_path):
    _write(tmp_path, "actions", [{"action": f"a{i}", "outcome": "done"} for i in range(30)])
    s = _state()
    assert len(s["recent_actions"]) == 20, "state is bounded so the prompt stays small"
    assert s["recent_actions"][-1]["action"] == "a29"


# --------------------------------------------------------------------------- runs

def test_record_run_writes_a_line(tmp_path):
    out = json.loads(fl.forge_loop_record_run(decision="chase the 12 stale leads",
                                              actions_taken=2, note="2 dry-run sends",
                                              next_check="reply rate"))
    assert out["success"] is True
    runs = _state()["last_runs"]
    assert len(runs) == 1
    assert runs[0]["decision"] == "chase the 12 stale leads"
    assert runs[0]["actions_taken"] == 2


def test_runs_are_bounded_in_state(tmp_path):
    for i in range(25):
        fl.forge_loop_record_run(decision=f"d{i}", actions_taken=1)
    assert len(_state()["last_runs"]) == 5, "only the last few runs are needed for context"


def test_decision_is_truncated(tmp_path):
    fl.forge_loop_record_run(decision="x" * 5000, actions_taken=0)
    assert len(_state()["last_runs"][0]["decision"]) == 1500


# --------------------------------------------------------------------------- resilience

def test_corrupt_ledger_line_is_skipped(tmp_path):
    p = tmp_path / "metrics.jsonl"
    p.write_text('{"metric":"ok","value":1}\nNOT JSON\n{"metric":"ok","value":2}\n', encoding="utf-8")
    m = _state()["metrics"]["ok"]
    assert m["latest"] == 2, "a corrupt line must not lose the good ones"


def test_state_never_raises_on_unreadable_dir(tmp_path, monkeypatch):
    """A path that is a FILE, not a directory — reads must degrade, not raise."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setenv("FORGE_LOOP_DIR", str(blocker))
    out = fl.forge_loop_state()          # must return JSON, not raise
    assert json.loads(out)["queue"]["pending"] == 0


def test_append_never_raises_when_dir_is_a_file(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir2"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("FORGE_LOOP_DIR", str(blocker))
    out = json.loads(fl.forge_loop_record_run(decision="d", actions_taken=0))
    assert out["success"] is True        # recorded in-memory; the ledger write failed silently


# --------------------------------------------------------------------------- registration

class _Ctx:
    def __init__(self):
        self.tools = []

    def register_tool(self, name, toolset, schema, handler, description="", **kw):
        self.tools.append((name, toolset, schema, handler))


def test_registers_the_three_tools():
    ctx = _Ctx()
    fl.register(ctx)
    assert {t[0] for t in ctx.tools} == {
        "forge_loop_state", "forge_loop_complete_action", "forge_loop_record_run"}


def test_tools_share_the_toolset():
    ctx = _Ctx()
    fl.register(ctx)
    assert {t[1] for t in ctx.tools} == {"forge_exec"}


def test_registered_handler_callable():
    ctx = _Ctx()
    fl.register(ctx)
    handler = next(h for n, _, _, h in ctx.tools if n == "forge_loop_state")
    assert json.loads(handler({}, task_id="t"))["queue"]["pending"] == 0
