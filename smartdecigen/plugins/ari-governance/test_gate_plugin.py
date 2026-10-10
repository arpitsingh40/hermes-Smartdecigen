"""Tests for the ari-governance plugin's decision logic.

These run without the Rust kernel and without Postgres: ``ask_kernel`` is monkeypatched, so
what's under test is the gate policy (which tools are gated, what each verdict turns into,
and whether failure fails closed).

Run:  python -m pytest test_gate_plugin.py -v
"""

import json
import os
import sys
import types

import pytest

# Import the plugin module directly from its directory (it is not an installed package).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as gate  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ARI_GATE_DISABLE", "ARI_GATE_FAIL_OPEN", "ARI_GATE_EXTRA_TOOLS",
                "ARI_JWT", "ARI_ORG_ID", "ARI_KERNEL_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ARI_JWT", "test-token")
    monkeypatch.setenv("ARI_ORG_ID", "org_test")
    yield


def _verdict(gate_value, reason=None, used=1.0, cap=10.0):
    return {"gate": gate_value, "reason": reason,
            "weekly_spend_used_usd": used, "weekly_spend_cap_usd": cap}


# --------------------------------------------------------------------------- gate table

def test_only_listed_tools_are_gated():
    assert gate.should_gate("send_email") == ("email.send", 0.01)
    assert gate.should_gate("video_generate")[0] == "video.generate"
    # Local/read-only tools must never be gated — that would put a network round-trip on
    # every turn and break the agent whenever the kernel is down.
    assert gate.should_gate("read_file") is None
    assert gate.should_gate("terminal") is None
    assert gate.should_gate("search_files") is None
    assert gate.should_gate("") is None


def test_extra_tools_from_env(monkeypatch):
    monkeypatch.setenv("ARI_GATE_EXTRA_TOOLS", "crm_write, ads_spend ,, ")
    table = gate.gated_actions()
    assert table["crm_write"] == ("crm_write", 0.01)
    assert table["ads_spend"] == ("ads_spend", 0.01)
    assert "" not in table


# --------------------------------------------------------------------------- verdicts

def test_allowed_lets_the_tool_through(monkeypatch):
    monkeypatch.setattr(gate, "ask_kernel", lambda *a, **k: _verdict("allowed"))
    assert gate._gate_verdict("send_email", {"to": "x"}) is None


def test_blocked_refuses_the_tool(monkeypatch):
    monkeypatch.setattr(gate, "ask_kernel",
                        lambda *a, **k: _verdict("blocked", "Weekly spend cap exceeded: $10.00 / $10.00"))
    out = gate._gate_verdict("send_email", {})
    assert out is not None and out["action"] == "block"
    assert "cap exceeded" in out["message"]
    assert "$10.00" in out["message"]


def test_dry_run_refuses_and_says_so(monkeypatch):
    monkeypatch.setattr(gate, "ask_kernel", lambda *a, **k: _verdict("dry_run", "dry-run active"))
    out = gate._gate_verdict("video_generate", {})
    assert out["action"] == "block"
    assert "DRY-RUN" in out["message"]


def test_unknown_verdict_fails_closed(monkeypatch):
    monkeypatch.setattr(gate, "ask_kernel", lambda *a, **k: _verdict("maybe_later"))
    out = gate._gate_verdict("send_email", {})
    assert out["action"] == "block"
    assert "unrecognised" in out["message"]


# --------------------------------------------------------------------------- failure policy

def test_kernel_unreachable_fails_closed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(gate, "ask_kernel", boom)
    out = gate._gate_verdict("send_email", {})
    assert out["action"] == "block"
    assert "fail-closed" in out["message"]
    assert "connection refused" in out["message"]


def test_fail_open_env_overrides_failure(monkeypatch):
    monkeypatch.setenv("ARI_GATE_FAIL_OPEN", "1")

    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(gate, "ask_kernel", boom)
    assert gate._gate_verdict("send_email", {}) is None


def test_disable_kill_switch_passes_everything(monkeypatch):
    monkeypatch.setenv("ARI_GATE_DISABLE", "1")

    def boom(*a, **k):
        raise AssertionError("kernel must not be called when disabled")
    monkeypatch.setattr(gate, "ask_kernel", boom)
    assert gate._gate_verdict("send_email", {}) is None


def test_ungated_tool_never_calls_the_kernel(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("kernel must not be called for an ungated tool")
    monkeypatch.setattr(gate, "ask_kernel", boom)
    assert gate._gate_verdict("read_file", {"path": "/tmp/x"}) is None


# --------------------------------------------------------------------------- spend commit

def test_spend_committed_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "commit_spend", lambda action, cost, **k: calls.append((action, cost)))
    gate.on_post_tool_call(tool_name="send_email", result=json.dumps({"success": True}), session_id="s1")
    assert calls == [("email.send", 0.01)]


def test_spend_not_committed_on_error_result(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "commit_spend", lambda action, cost, **k: calls.append((action, cost)))
    gate.on_post_tool_call(tool_name="send_email", result=json.dumps({"error": "smtp down"}))
    assert calls == []


def test_spend_not_committed_for_ungated_tool(monkeypatch):
    calls = []
    monkeypatch.setattr(gate, "commit_spend", lambda action, cost, **k: calls.append((action, cost)))
    gate.on_post_tool_call(tool_name="read_file", result="contents")
    assert calls == []


# --------------------------------------------------------------------------- hook safety

def test_hook_never_raises(monkeypatch):
    """A hook that raises would break the agent loop; the wrapper must swallow and pass through."""
    monkeypatch.setattr(gate, "should_gate", lambda name: (_ for _ in ()).throw(RuntimeError("kaboom")))
    assert gate.on_pre_tool_call(tool_name="send_email") is None
