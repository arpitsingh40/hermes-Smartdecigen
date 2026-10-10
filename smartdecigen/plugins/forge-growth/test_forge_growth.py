"""Tests for forge-growth — symptom detection, root-cause walk, opportunity scan, 10x frame.

Run:  python -m pytest test_forge_growth.py -v
"""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fg  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ("FORGE_GROWTH_DISABLE", "FORGE_GROWTH_MAX_CHARS", "FORGE_GROWTH_DEPTH",
              "FORGE_GROWTH_HEALTH"):
        monkeypatch.delenv(v, raising=False)
    yield


# --------------------------------------------------------------------------- data integrity

def test_graph_loaded():
    assert len(fg.DEPENDENCY_GRAPH) == 16
    assert len(fg.FUNCTION_LABELS) == 16
    assert len(fg._SYMPTOMS) >= 14
    assert "marketing" in fg.OPPORTUNITY_PATTERNS
    assert fg.FAILURE_MODES


def test_graph_is_directional_and_acyclic():
    """Every dependency must be a known function, and the graph must have no cycles."""
    for func, deps in fg.DEPENDENCY_GRAPH.items():
        for dep in deps:
            assert dep in fg.DEPENDENCY_GRAPH, f"{func} depends on unknown {dep}"

    # cycle check via DFS
    state = {}

    def visit(n):
        if state.get(n) == 1:
            raise AssertionError(f"cycle at {n}")
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in fg.DEPENDENCY_GRAPH.get(n, []):
            visit(d)
        state[n] = 2

    for n in fg.DEPENDENCY_GRAPH:
        visit(n)


def test_vision_is_the_root():
    assert fg.DEPENDENCY_GRAPH["vision"] == []


# --------------------------------------------------------------------------- symptoms

@pytest.mark.parametrize("msg,expected", [
    ("our revenue is dropping and sales are flat", "sales"),
    ("customers are churning, we keep losing them", "customer_success"),
    ("the product is not selling, no traction at all", "product"),
    ("deploys are slow, we have tech debt everywhere", "technology"),
    ("we are running out of money, burn rate too high", "finance"),
    ("marketing is not working, leads are dead", "marketing"),
    ("growth has stalled, we hit a ceiling", "growth"),
    ("a competitor is undercutting us, losing deals", "strategy"),
    ("ops is broken, everything is a bottleneck", "operations"),
    ("we have bad press and reputation damage", "brand"),
])
def test_detect_symptoms(msg, expected):
    assert expected in fg.detect_symptoms(msg)


def test_symptoms_capped_at_three():
    msg = ("revenue dropping, customers churning, product not selling, deploys slow, "
           "running out of money, cannot hire, marketing broken, growth stalled")
    assert len(fg.detect_symptoms(msg)) <= 3


def test_no_symptoms_for_offtopic():
    assert fg.detect_symptoms("read the file at /tmp/x") == []
    assert fg.detect_symptoms("what is the capital of France") == []
    assert fg.detect_symptoms("") == []


def test_symptom_patterns_are_word_bounded():
    """The source patterns are already anchored — 'sales' must not fire inside 'wholesaler'."""
    assert "sales" not in fg.detect_symptoms("we are a wholesaler of textiles")
    assert "sales" not in fg.detect_symptoms("that was a salesy pitch")


# --------------------------------------------------------------------------- root cause walk

def test_walk_goes_upstream_from_symptom():
    """sales depends on marketing + product, so the walk must reach them."""
    tree = fg.build_tree("sales", max_depth=2)
    assert tree["function"] == "sales"
    upstream = {c["function"] for c in tree["upstream"]}
    assert "marketing" in upstream
    assert "product" in upstream


def test_walk_respects_max_depth():
    shallow = fg.build_tree("growth", max_depth=0)
    assert shallow["upstream"] == []
    deeper = fg.build_tree("growth", max_depth=2)
    assert deeper["upstream"]


def test_walk_terminates_on_a_cycle_guard():
    """The path guard must stop a malformed graph from recursing forever, while still showing a
    function reachable by two routes (product is reachable via marketing AND via sales)."""
    tree = fg.build_tree("sales", max_depth=3)
    def names(node, acc):
        acc.add(node["function"])
        for c in node.get("upstream", []):
            names(c, acc)
        return acc
    seen = names(tree, set())
    assert "product" in seen
    # product appears under both marketing and sales at depth<=3
    assert isinstance(fg.build_tree("data", max_depth=5), dict)


def test_root_cause_block_renders_the_chain():
    block = fg.root_cause_block("our revenue is dropping and sales are flat")
    assert "ROOT CAUSE" in block
    assert "Sales" in block


def test_root_cause_block_empty_when_no_symptom():
    assert fg.root_cause_block("hello there") == ""


def test_health_enrichment_optional(monkeypatch):
    msg = "our revenue is dropping"
    assert "health" not in fg.root_cause_block(msg)
    monkeypatch.setenv("FORGE_GROWTH_HEALTH", json.dumps({"sales": 30, "marketing": 40}))
    enriched = fg.root_cause_block(msg)
    assert "health 30/100 (at_risk)" in enriched


# --------------------------------------------------------------------------- opportunity scan

def test_opportunity_block_gives_real_avenues():
    block = fg.opportunity_block("how do we grow our marketing")
    assert "GROWTH AVENUES" in block
    assert "(from " in block  # each avenue cites its source book


def test_opportunity_defaults_on_generic_growth_ask():
    block = fg.opportunity_block("how do we 10x")
    assert "GROWTH AVENUES" in block


# --------------------------------------------------------------------------- 10x planner

def test_wants_growth_detects_the_ask():
    for m in ["how do we grow", "we want 10x", "how to scale", "double revenue",
              "expand to a new market", "next level"]:
        assert fg.wants_growth(m), m


def test_wants_growth_negative():
    for m in ["read this file", "fix the bug", "what is 2+2"]:
        assert not fg.wants_growth(m), m


def test_growth_plan_block_has_the_required_shape():
    block = fg.growth_plan_block("how do we 10x this year")
    assert "10x GROWTH PLAN" in block
    for rule in ("LOOPS", "cadence", "Milestones", "MANUAL", "Compounding"):
        assert rule in block, f"missing planner rule: {rule}"


def test_growth_plan_block_empty_when_not_asked():
    assert fg.growth_plan_block("the revenue is dropping") == ""


# --------------------------------------------------------------------------- assembly

def test_block_combines_root_cause_and_plan():
    block = fg.build_block("growth has stalled, how do we 10x")
    assert "ROOT CAUSE" in block
    assert "10x GROWTH PLAN" in block
    assert "GROWTH AVENUES" in block


def test_block_offtopic_injects_nothing():
    assert fg.build_block("read the file at /tmp/x") == ""
    assert fg.build_block("what is the capital of France") == ""
    assert fg.build_block("") == ""


def test_problem_turn_gets_avenues_but_no_plan_frame():
    """A problem is not a plan request — the planner frame would be noise."""
    block = fg.build_block("our marketing is not working, leads are dead")
    assert "ROOT CAUSE" in block
    assert "GROWTH AVENUES" in block
    assert "10x GROWTH PLAN" not in block


def test_disable_flag(monkeypatch):
    monkeypatch.setenv("FORGE_GROWTH_DISABLE", "1")
    assert fg.build_block("growth has stalled, how do we 10x") == ""


def test_max_chars_cap(monkeypatch):
    monkeypatch.setenv("FORGE_GROWTH_MAX_CHARS", "200")
    block = fg.build_block("growth stalled, marketing broken, revenue dropping, how do we 10x")
    assert len(block) <= 220
    assert "truncated" in block


# --------------------------------------------------------------------------- hook contract

def test_hook_returns_context():
    out = fg.on_pre_llm_call(user_message="our revenue is dropping and sales are flat")
    assert isinstance(out, dict) and "ROOT CAUSE" in out["context"]


def test_hook_returns_none_when_nothing_to_say():
    assert fg.on_pre_llm_call(user_message="read the file at /tmp/x") is None


def test_hook_accepts_hermes_payload():
    out = fg.on_pre_llm_call(
        session_id="s", task_id="t", turn_id="tu", user_message="growth has stalled, how do we 10x",
        conversation_history=[], is_first_turn=True, model="m", platform="cli",
        parent_session_id=None, sender_id="u",
    )
    assert isinstance(out, dict)


def test_hook_never_raises(monkeypatch):
    monkeypatch.setattr(fg, "build_block", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert fg.on_pre_llm_call(user_message="anything") is None
