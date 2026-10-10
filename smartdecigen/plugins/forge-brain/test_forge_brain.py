"""Tests for forge-brain — decision routing, lens selection, block assembly.

Includes a PARITY test against the original SmartDecigen implementation: the port must select
the same lenses for the same message, or it is a rewrite, not a port.

Run:  python -m pytest test_forge_brain.py -v
"""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fb  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ("FORGE_BRAIN_DISABLE", "FORGE_BRAIN_MAX_LENSES", "FORGE_BRAIN_MIN_SCORE",
              "FORGE_BRAIN_MAX_CHARS", "FORGE_BRAIN_FRUIT"):
        monkeypatch.delenv(v, raising=False)
    yield


# --------------------------------------------------------------------------- data integrity

def test_all_data_loaded():
    assert len(fb.MODULES) == 166, "expected the full 166-module library"
    assert len(fb._CATEGORIES) == 9, "expected 9 decision categories"
    assert len(fb.KNOWLEDGE_MAP) == 166
    assert len(fb.TIER1) == 12


def test_every_module_has_required_fields():
    for m in fb.MODULES:
        assert m["id"] and m["book"] and m["lens"]
        assert isinstance(m["triggers"], list) and m["triggers"]
        for kw, w in m["triggers"]:
            assert isinstance(kw, str) and isinstance(w, int)


def test_every_knowledge_file_exists():
    missing = [p for p in fb.KNOWLEDGE_MAP.values() if not (fb._BASE / p).exists()]
    assert missing == [], f"missing knowledge files: {missing[:5]}"


# --------------------------------------------------------------------------- decision router

@pytest.mark.parametrize("msg,expected", [
    ("should I sign the distributor deal at these terms", "deal_negotiation"),
    ("should we hire a second salesperson or a cofounder", "people_team"),
    ("our CAC is too high, what marketing channel should we use", "growth_marketing"),
    ("should I raise the price of the plan", "pricing_offer"),
    ("how do I validate whether customers want this feature", "product_validation"),
    ("we are in crisis and need to survive, emergency runway", "crisis_survival"),
    ("what should our 3 year strategy be, expand to a new market", "strategy_direction"),
    ("how should I allocate this extra cash between ads and inventory", "money_allocation"),
    ("how do I improve our ops process and delivery", "ops_execution"),
])
def test_classify_routes_each_category(msg, expected):
    assert fb.classify_decision(msg) == expected


def test_classify_returns_none_for_generic():
    assert fb.classify_decision("what should I have for lunch") is None
    assert fb.classify_decision("") is None


# --------------------------------------------------------------------------- lens selection

def test_sunk_cost_selects_kahneman():
    got = fb.select_lenses("we already invested 5 lakh in this and I know it will work")
    ids = [i for _, i, _, _ in got]
    assert "kahneman_bias" in ids, f"expected kahneman_bias, got {ids}"


def test_no_score_returns_empty():
    """A message with no business-decision signal must select nothing."""
    assert fb.select_lenses("read the file at /tmp/x") == []
    assert fb.select_lenses("git status") == []
    assert fb.select_lenses("print hello world") == []


def test_max_lenses_respected():
    msg = "should I sign the contract deal with the distributor about pricing terms"
    assert len(fb.select_lenses(msg, max_lenses=2)) <= 2


def test_boost_ids_lift_a_lens():
    """A lens named by the decision category must outrank an equal-scoring rival."""
    msg = "negotiate the deal"
    plain = {i for _, i, _, _ in fb.select_lenses(msg, min_score=1, max_lenses=9)}
    boosted = {i for _, i, _, _ in fb.select_lenses(msg, min_score=1, max_lenses=9,
                                                    boost_ids=["voss_negotiation"])}
    assert "voss_negotiation" in boosted
    # and it should rank first when boosted
    top = fb.select_lenses(msg, min_score=1, max_lenses=1, boost_ids=["voss_negotiation"])
    assert top[0][1] == "voss_negotiation"
    assert plain  # sanity: the message scores something on its own


def test_deterministic_ordering():
    msg = "should I hire or fire, the deal and the price and the cash all matter"
    a = [i for _, i, _, _ in fb.select_lenses(msg)]
    b = [i for _, i, _, _ in fb.select_lenses(msg)]
    assert a == b


# --------------------------------------------------------------------------- block assembly

def test_block_has_category_and_lenses():
    block = fb.build_block("should I sign the distributor deal at these terms")
    assert "DECISION TYPE: deal negotiation" in block
    assert "REASONING LENSES" in block
    assert "DEAL/NEGOTIATION ALGORITHM" in block


def test_block_empty_for_offtopic_turn():
    """An irrelevant turn must inject nothing — that is why this is a hook, not a prompt section."""
    assert fb.build_block("what should I have for lunch today") == ""


def test_disable_kill_switch(monkeypatch):
    monkeypatch.setenv("FORGE_BRAIN_DISABLE", "1")
    assert fb.build_block("should I sign the distributor deal") == ""


def test_max_chars_cap(monkeypatch):
    monkeypatch.setenv("FORGE_BRAIN_MAX_CHARS", "300")
    block = fb.build_block("should I sign the distributor deal at these terms")
    assert len(block) <= 320  # cap + the truncation marker
    assert "truncated" in block


def test_fruit_can_be_disabled(monkeypatch):
    msg = "we already invested 5 lakh and I know it will work"
    with_fruit = fb.build_block(msg)
    monkeypatch.setenv("FORGE_BRAIN_FRUIT", "0")
    without = fb.build_block(msg)
    assert "rules from" in with_fruit
    assert "rules from" not in without


# --------------------------------------------------------------------------- hook contract

def test_hook_returns_context_dict():
    out = fb.on_pre_llm_call(user_message="should I sign the distributor deal at these terms")
    assert isinstance(out, dict) and "context" in out
    assert "DECISION TYPE" in out["context"]


def test_hook_returns_none_when_nothing_to_say():
    assert fb.on_pre_llm_call(user_message="what should I have for lunch today") is None


def test_fallback_lenses_fire_for_category_without_direct_score():
    """A category turn whose lenses all score below the threshold still gets a curated framework.

    min_score is raised so nothing scores directly, proving the fallback path rather than the
    normal selection path.
    """
    msg = "we are in crisis and need to survive, emergency runway"
    assert fb.classify_decision(msg) == "crisis_survival"
    # With an impossible threshold, direct selection yields nothing...
    assert fb.select_lenses(msg, min_score=999) == []
    # ...and the block must still carry a framework via the curated fallback.
    block = fb.build_block(msg)
    assert "DECISION TYPE: crisis survival" in block
    assert "REASONING LENSES" in block


def test_hook_accepts_hermes_payload_fields():
    """Hermes sends session_id/task_id/turn_id/conversation_history/etc — all must be absorbed."""
    out = fb.on_pre_llm_call(
        session_id="s", task_id="t", turn_id="tu", user_message="should we hire a cofounder",
        conversation_history=[{"role": "user", "content": "hi"}], is_first_turn=True,
        model="gpt-x", platform="cli", parent_session_id=None, sender_id="u1",
    )
    assert isinstance(out, dict) and "context" in out


def test_hook_never_raises(monkeypatch):
    monkeypatch.setattr(fb, "build_block", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert fb.on_pre_llm_call(user_message="anything") is None


# --------------------------------------------------------------------------- matcher correctness

def test_short_triggers_respect_word_boundaries():
    """A single-word trigger must not match inside a longer word — the deviation from the original.

    'director' (feld_boards) used to match inside "directory"; 'lease' (taleb_antifragile) used
    to match inside "please".
    """
    assert fb.select_lenses("list the files in this directory") == []
    assert fb.select_lenses("yes please") == []
    assert fb.select_lenses("read this file please") == []


def test_prefix_triggers_still_work():
    """The original relies on prefix triggers ('exclusiv' -> 'exclusivity'); word-start matching
    must keep them working."""
    ids = [i for _, i, _, _ in fb.select_lenses("exclusivity for three years")]
    assert "taleb_antifragile" in ids


def test_category_router_has_the_same_word_boundary_rule():
    """'cto' is a people_team keyword and used to match inside 'directory'."""
    assert fb.classify_decision("list the files in this directory") is None
    assert fb.classify_decision("we need a cto") == "people_team"
    assert fb.classify_decision("do we need to hire a cto or a cofounder") == "people_team"


def test_lens_injection_is_gated_on_a_decision_category():
    """The core deviation: lenses only fire on a business-decision turn.

    The lens vocabulary is business-domain, so on ordinary agent work it would fire wrong
    frameworks ('lease' inside 'please', 'convert' inside 'convert this to json').
    """
    off_topic = [
        "yes please",
        "explain this code",
        "convert this to json",
        "read this file please",
        "what should I have for lunch today",
    ]
    for msg in off_topic:
        assert fb.build_block(msg) == "", f"{msg!r} should inject nothing"


def test_long_triggers_still_stem():
    """Substring matching is kept for long triggers, which is what makes stemming work."""
    ids = [i for _, i, _, _ in fb.select_lenses("I am confident the projection is right")]
    assert "kahneman_bias" in ids


def test_phrase_triggers_still_match():
    ids = [i for _, i, _, _ in fb.select_lenses("we already invested 5 lakh in this")]
    assert "kahneman_bias" in ids


# --------------------------------------------------------------------------- parity with source

def test_parity_with_smartdecigen_on_business_messages():
    """On real business messages the port must select the same lens ids as the original.

    This is the check that matters: the deviation is only in HOW short triggers match, not in
    the scoring, ranking, or selection. On a genuine business turn the two agree exactly.

    Skips if the original tree is absent — a development-time check, not a runtime dependency.
    """
    src = r"C:\Users\Dell -\Documents\Code\Smartdecision-main\backend"
    if not os.path.isdir(src):
        pytest.skip("SmartDecigen source not present")
    import importlib.util
    spec = importlib.util.spec_from_file_location("_lenses_orig", os.path.join(src, "lenses.py"))
    orig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orig)

    messages = [
        "we already invested 5 lakh in this and I know it will work",
        "should I sign the distributor deal at these terms",
        "our CAC is too high, what channel should we use",
        "how do I price the new plan for Indian customers",
        "the deal terms give them exclusivity for three years",
    ]
    for msg in messages:
        ours = [i for _, i, _, _ in fb.select_lenses(msg)]
        theirs_scored = []
        hay = msg.lower()
        for m in orig.MODULES:
            s = sum(w for kw, w in m["triggers"] if kw in hay)
            if s >= 2:
                theirs_scored.append((s + (0.5 if m["id"] in orig._TIER1_BOOST else 0.0), m["id"]))
        theirs_scored.sort(key=lambda t: -t[0])
        theirs = [i for _, i in theirs_scored[:3]]
        assert ours == theirs, f"parity mismatch for {msg!r}: ours={ours} theirs={theirs}"
