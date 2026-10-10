"""Tests for forge-confirm — the final quality gate.

The gate is OFF by default (it costs an LLM call per turn) and fails OPEN (any error keeps the
draft). Both properties are asserted here, because getting either wrong is expensive: an
always-on gate multiplies cost, and a fail-closed gate can blank a good reply.

Run:  python -m pytest test_forge_confirm.py -v
"""

import os
import sys
from types import SimpleNamespace

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fc  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ("FORGE_CONFIRM", "FORGE_CONFIRM_MAX_TOKENS", "FORGE_CONFIRM_TIMEOUT"):
        monkeypatch.delenv(v, raising=False)
    yield


class _LLM:
    """Stands in for ctx.llm — records calls, returns a scripted result or raises."""

    def __init__(self, parsed=None, raise_exc=None):
        self.parsed = parsed
        self.raise_exc = raise_exc
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return SimpleNamespace(parsed=self.parsed, text="raw")


class _Ctx:
    def __init__(self, llm=None):
        self.llm = llm or _LLM()
        self.hooks = {}

    def register_hook(self, name, cb):
        self.hooks[name] = cb


DRAFT = ("Here is a long enough draft reply that clears the minimum length check so the gate "
         "will actually consider confirming it against the user's question.")

QUESTION = "what should I do about the distributor deal?"


@pytest.fixture(autouse=True)
def clear_stash():
    fc._STASH.clear()
    yield
    fc._STASH.clear()


# --------------------------------------------------------------------------- off by default

def test_disabled_by_default():
    assert fc.should_check(DRAFT, QUESTION) is False


def test_disabled_means_no_llm_call(monkeypatch):
    ctx = _Ctx()
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    out = ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s")
    assert out is None
    assert ctx.llm.calls == [], "no LLM call may happen while disabled"


def test_enabled_via_env(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    assert fc.should_check(DRAFT, QUESTION) is True


# --------------------------------------------------------------------------- the stash bridge

def test_stash_carries_the_message_between_hooks(monkeypatch):
    """The whole point of the two-hook design: pre_llm_call stashes, transform reads."""
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    better = DRAFT + " Sharper ending."
    ctx = _Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": better}))
    fc.register(ctx)

    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s1")
    out = ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s1")

    assert out == better
    # and the gate saw the real question, not a blank
    sent = ctx.llm.calls[0]["input"][0]["text"]
    assert "distributor deal" in sent


def test_without_the_stash_the_gate_declines(monkeypatch):
    """No pre_llm_call means no question — decline rather than rewrite blind."""
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx()
    fc.register(ctx)
    out = ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="never-stashed")
    assert out is None
    assert ctx.llm.calls == []


def test_stash_is_keyed_by_session(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": DRAFT + " x"}))
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message="session one question", session_id="s1")
    ctx.hooks["pre_llm_call"](user_message="session two question", session_id="s2")
    ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s2")
    assert "session two" in ctx.llm.calls[0]["input"][0]["text"]


def test_stash_ttl_expiry(monkeypatch):
    """Control the clock rather than sleeping — the TTL has a 1s floor by design."""
    stash = fc.MessageStash(max_entries=4, ttl_seconds=10)
    clock = {"t": 1000.0}
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["t"])
    stash.put("k", "hello")
    assert stash.get("k") == "hello"
    clock["t"] += 11          # past the 10s TTL
    assert stash.get("k") == ""
    assert len(stash) == 0    # expired entries are dropped, not just hidden


def test_stash_lru_bound():
    stash = fc.MessageStash(max_entries=2, ttl_seconds=60)
    stash.put("a", "1"); stash.put("b", "2"); stash.put("c", "3")
    assert len(stash) == 2
    assert stash.get("a") == ""      # evicted (LRU)
    assert stash.get("c") == "3"


def test_stash_falls_back_to_default_key():
    assert fc._stash_key("", "") == "_default"
    assert fc._stash_key("", "task") == "task"
    assert fc._stash_key("sess", "task") == "sess"


# --------------------------------------------------------------------------- pre-checks

@pytest.mark.parametrize("draft,msg", [
    ("", QUESTION),
    ("   ", QUESTION),
    ("too short", QUESTION),
    (DRAFT, ""),
    (DRAFT, "   "),
])
def test_prechecks_decline(monkeypatch, draft, msg):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    assert fc.should_check(draft, msg) is False


def test_very_long_draft_declined(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    assert fc.should_check("x" * 9000, QUESTION) is False


# --------------------------------------------------------------------------- behaviour

def test_kept_verdict_returns_none(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    assert fc.run_gate(DRAFT, QUESTION, ctx=_Ctx(llm=_LLM(parsed={"verdict": "kept", "reply": DRAFT}))) is None


def test_improved_verdict_replaces_the_reply(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    better = DRAFT + " And here is the sharpened ending."
    got = fc.run_gate(DRAFT, QUESTION, ctx=_Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": better})))
    assert got == better


def test_identical_reply_returns_none(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    got = fc.run_gate(DRAFT, QUESTION, ctx=_Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": DRAFT + "  "})))
    assert got is None


# --------------------------------------------------------------------------- fail OPEN

def test_llm_error_keeps_the_draft(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx(llm=_LLM(raise_exc=RuntimeError("provider down")))
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    assert ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s") is None


def test_unparsed_response_keeps_the_draft(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx(llm=_LLM(parsed=None))
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    assert ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s") is None


def test_empty_reply_from_model_keeps_the_draft(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": "   "}))
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    assert ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s") is None


def test_hook_never_raises(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx()
    fc.register(ctx)
    monkeypatch.setattr(fc, "run_gate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    assert ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s") is None


def test_pre_hook_never_raises(monkeypatch):
    ctx = _Ctx()
    fc.register(ctx)
    monkeypatch.setattr(fc._STASH, "put", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s") is None


# --------------------------------------------------------------------------- contract

def test_registers_both_hooks():
    ctx = _Ctx()
    fc.register(ctx)
    assert set(ctx.hooks) == {"pre_llm_call", "transform_llm_output"}


def test_call_passes_the_audit_purpose(monkeypatch):
    monkeypatch.setenv("FORGE_CONFIRM", "1")
    ctx = _Ctx(llm=_LLM(parsed={"verdict": "improved", "reply": DRAFT + " x"}))
    fc.register(ctx)
    ctx.hooks["pre_llm_call"](user_message=QUESTION, session_id="s")
    ctx.hooks["transform_llm_output"](response_text=DRAFT, session_id="s")
    assert ctx.llm.calls[0]["purpose"] == "forge.confirm"
    assert ctx.llm.calls[0]["json_schema"] is fc.CONFIRM_SCHEMA
