"""forge-brain — decision-science reasoning lenses, applied per turn.

Ported from SmartDecigen's `lenses.py` + `cognition.py`. The value is not the prompt; it is
WHAT GOES INTO the prompt. This plugin assembles, at zero LLM cost, the two layers that turn a
generic model into one that reasons like a specific operator:

  decision category  — a keyword router into 9 founder decision types, each carrying a
                       step-by-step reasoning algorithm
  reasoning lenses   — the 3 most relevant modules from a 166-book decision-science library,
                       scored against the turn's message and injected as applied frameworks

Both ride ``pre_llm_call``, which Hermes documents as injecting into the USER MESSAGE — not the
system prompt. That is deliberate and load-bearing: Hermes' prompt-caching invariant forbids
rebuilding the system prompt mid-conversation, and this content is different every turn. Putting
it in the system prompt would break the cached prefix and multiply the user's cost.

Data lives in ``lenses.json`` (166 modules, triggers + lens instruction) and
``categories.json`` (9 categories, keywords + algorithm). The knowledge FRUIT rules live under
``knowledge/`` and are injected only for the lenses that actually fired, so an off-topic turn
costs nothing.

Env:
  FORGE_BRAIN_DISABLE=1     kill switch — no context injected
  FORGE_BRAIN_MAX_LENSES    how many lenses to inject (default 3)
  FORGE_BRAIN_MIN_SCORE     minimum trigger score to select a lens (default 2)
  FORGE_BRAIN_MAX_CHARS     hard cap on the injected block (default 2400)
  FORGE_BRAIN_FRUIT=0       skip the knowledge FRUIT rules (lens text only)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Data loading (once, at import)
# ---------------------------------------------------------------------------

def _load_json(name: str) -> Any:
    try:
        with open(_BASE / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001 - a missing data file must not crash the agent
        logger.error("forge-brain: cannot load %s: %s", name, exc)
        return None


_LENSES = _load_json("lenses.json") or {}
_CATEGORIES = _load_json("categories.json") or {}

MODULES: List[Dict[str, Any]] = _LENSES.get("modules", [])
TIER1: frozenset = frozenset(_LENSES.get("tier1_boost", []))
KNOWLEDGE_MAP: Dict[str, str] = _LENSES.get("knowledge_map", {})

# ---------------------------------------------------------------------------
# The decision-category router — and why it is NARROWED
#
# A decision category is a strong claim: "this message is a deal negotiation." Getting it wrong
# is worse than staying silent, because it injects a confident reasoning algorithm AND three
# book lenses into a turn that has nothing to do with them.
#
# The source keyword list was written for a business-coaching conversation where every message
# is about the business. In a general-purpose agent it fires constantly on ordinary work, because
# several category keywords are bare common English words that also appear in code, paths, and
# build output. Measured on real agent text, 8 of 10 off-topic messages were misclassified:
#
#   "vendor-react-...js"          -> deal_negotiation   (the word "vendor")
#   "check the deal-chart.tsx"    -> deal_negotiation   (the word "deal")
#   "the contract test passed"    -> deal_negotiation   (the word "contract")
#   "fix the offer-calculator"    -> pricing_offer      (the word "offer")
#   "update the pricing-page"     -> pricing_offer      (the word "price")
#   "fix hiring flow"             -> people_team        (the word "hire")
#
# Fix: a keyword that is a bare COMMON ENGLISH WORD only counts when the message also looks like
# a business-decision turn. Distinctive multi-word keywords ("distributor", "counter offer",
# "cofounder", "runway") still match on their own — they are unambiguous.
# ---------------------------------------------------------------------------

# Single-word category keywords that are too common to trust alone.
_AMBIGUOUS = frozenset({
    "deal", "contract", "terms", "vendor", "price", "offer", "hire", "invest", "budget",
    "team", "member", "convert", "code", "plan", "build", "run", "test", "fix", "sales",
})

# Signals that this really is a business turn rather than code, paths, or build output.
_BUSINESS_SIGNALS = (
    # first-person business framing
    "should i", "should we", "my business", "our business", "my company", "our company",
    "my startup", "our startup", "my revenue", "our revenue", "my customer", "our customer",
    "my team", "our team", "i want to", "we want to", "i need to decide", "help me decide",
    "what do you think", "is it worth", "worth it", "should we sign", "should i sign",
    # business nouns that rarely appear in code
    "customer", "client", "revenue", "profit", "margin", "cash flow", "runway", "pricing",
    "competitor", "market", "investor", "funding", "valuation", "invoice", "payroll",
    "supplier", "distributor", "partnership", "negotiat", "employee", "candidate",
    "salary", "equity", "churn", "retention", "funnel", "campaign", "acquisition",
    "invested", "investment", "lakh", "crore", "money",
)


def _looks_like_business(text: str) -> bool:
    return any(sig in text for sig in _BUSINESS_SIGNALS)


# NOTE: the category matcher and router are defined BELOW, after _SUFFIXES and _COMPILED,
# because they reuse the same whole-word+suffix matcher as the lens triggers.

# Trigger matching — DELIBERATE DEVIATION from the original implementation, in two places.
#
# The original matched every trigger as a plain substring, and injected lenses whenever any
# module scored. That is harmless in a business-coaching conversation where every message is
# about the business. In a general-purpose agent it produces confident nonsense: the lens
# vocabulary is business-domain ("lease", "convert", "director", "code", "should i"), so on
# ordinary agent work it fires wrong frameworks.
#
#   'lease'  matched inside "please"        -> taleb_antifragile on "yes please"
#   'director' matched inside "directory"   -> feld_boards on "list the files in this directory"
#   'convert' matched "convert this to json"-> bush_plg + cialdini_influence on a file task
#   'code'   matched "explain this code"    -> feathers_legacy on a question about source
#
# Two fixes, both in this file:
#   1. A SINGLE-WORD trigger matches a WHOLE WORD, optionally followed by a common English
#      suffix. That stops 'director' matching inside "directory" and 'lease' inside "please",
#      while keeping intentional prefix triggers ('exclusiv' -> "exclusivity") and stemming
#      ('confident' -> "confidence", 'estimate' -> "estimates") intact. Multi-word PHRASE
#      triggers keep plain substring matching ('already invested').
#   2. Lenses are injected only when the message also routes to a DECISION CATEGORY (see
#      build_block). The category keywords are specific business terms ("runway", "cofounder",
#      "CAC"), so they gate the generic lens vocabulary to turns that are actually about a
#      business decision. Off-topic agent work injects nothing.
_COMPILED: List[Tuple[str, str, Tuple[Tuple[Any, int], ...], str]] = []

# Suffixes allowed after a single-word trigger. 'y' is deliberately absent so 'director' does
# not match "directory"; 'ity' is present so 'exclusiv' does match "exclusivity".
_SUFFIXES = ("s", "es", "ed", "ing", "ly", "ity", "ion", "ive", "ment", "al", "er", "est")


def _matcher(kw: str):
    """Predicate for one trigger: whole-word (+ known suffix) for single words, substring for phrases."""
    if " " not in kw:
        alt = "|".join(_SUFFIXES)
        rx = re.compile(rf"\b{re.escape(kw)}(?:{alt})?\b")
        return rx.search
    return lambda hay, _kw=kw: _kw in hay


for _m in MODULES:
    _COMPILED.append((
        _m["id"], _m["book"],
        tuple((_matcher(k), w) for k, w in _m["triggers"]),
        _m["lens"],
    ))


# ---------------------------------------------------------------------------
# Category router (defined here because it reuses _SUFFIXES / _matcher)
# ---------------------------------------------------------------------------

_CATEGORY_COMPILED: Dict[str, Tuple[Tuple[Any, int], ...]] = {
    cat: tuple((_matcher(kw), 1) for kw in spec["kw"])
    for cat, spec in _CATEGORIES.items()
}


def classify_decision(text: str) -> Optional[str]:
    """Keyword router into a decision category. Highest hit count wins; None when nothing hits.

    Ported from cognition.py::classify_decision (same scoring: count matching keywords per
    category, take the max, require >= 1). Two deviations, both to survive a general-purpose
    host: whole-word matching (see _matcher), and the _AMBIGUOUS gate — a bare common English
    keyword only counts on a message that also reads as a business turn.
    """
    hay = (text or "").lower()
    business = _looks_like_business(hay)
    best, best_score = None, 0
    for cat, compiled in _CATEGORY_COMPILED.items():
        spec = _CATEGORIES[cat]
        score = 0
        for (match, _), kw in zip(compiled, spec["kw"]):
            if not match(hay):
                continue
            # A bare common word only counts on a business-looking turn.
            if kw in _AMBIGUOUS and not business:
                continue
            score += 1
        if score > best_score:
            best, best_score = cat, score
    return best if best_score >= 1 else None

_FRUIT_RE = re.compile(r"## FRUIT[^\n]*\n(.*?)(?=\n## |\Z)", re.DOTALL)
_fruit_cache: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Pure logic — no Hermes dependency, so it is unit-testable in isolation
# ---------------------------------------------------------------------------

def load_fruit(filepath: str) -> str:
    """Read the FRUIT (actionable WHEN→APPLY rules) section from a knowledge file."""
    if filepath in _fruit_cache:
        return _fruit_cache[filepath]
    try:
        text = (_BASE / filepath).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        _fruit_cache[filepath] = ""
        return ""
    m = _FRUIT_RE.search(text)
    out = m.group(1).strip() if m else ""
    _fruit_cache[filepath] = out
    return out


def select_lenses(
    message: str,
    model: Optional[Dict[str, Any]] = None,
    max_lenses: int = 3,
    min_score: int = 2,
    boost_ids: Optional[List[str]] = None,
) -> List[Tuple[int, str, str, str]]:
    """Score every module against the message; return the top N as (score, id, book, lens).

    Ported from lenses.py::select_lenses, minus the two SmartDecigen-only couplings
    (``function_health`` → business_taxonomy, dropped here; that belongs to the business-graph
    port). ``boost_ids`` are the lens ids preferred by the detected decision category (+3).
    """
    hay = (message or "").lower()
    if model:
        try:
            hay += " " + json.dumps(model, ensure_ascii=False, default=str).lower()
        except Exception:  # noqa: BLE001
            pass
    boosts = set(boost_ids or [])

    scored: List[Tuple[float, str, str, str]] = []
    for lens_id, book, triggers, lens in _COMPILED:
        s = sum(w for match, w in triggers if match(hay))
        if lens_id in boosts:
            s += 3
        if s >= min_score:
            scored.append((s + (0.5 if lens_id in TIER1 else 0.0), lens_id, book, lens))
    if not scored:
        return []
    # Faithful to the original: sort by score alone. Python's sort is stable, so ties keep
    # MODULES order — sorting by id here would silently reorder tied lenses and diverge
    # from the source implementation.
    scored.sort(key=lambda t: -t[0])
    return [(int(s), i, b, l) for s, i, b, l in scored[:max_lenses]]


# Fallback lens ids for a message that names a problem but scores no lens directly.
# Without this, "we are running out of cash and might miss payroll" injects nothing —
# exactly the turn where a reasoning framework matters most.
_FALLBACK_LENSES: Dict[str, List[str]] = {
    "crisis_survival": ["taleb_antifragile", "munger_incentives", "essentialism"],
    "money_allocation": ["munger_incentives", "thorndike_capital", "essentialism"],
    "strategy_direction": ["rumelt_kernel", "seven_powers", "playing_to_win"],
    "deal_negotiation": ["munger_incentives", "voss_negotiation", "art_of_war"],
    "people_team": ["dalio_principles", "grove_highoutput", "who_method"],
    "growth_marketing": ["purple_cow", "positioning", "traction"],
    "pricing_offer": ["priceless", "monetizing_innovation", "strategy_tactics_pricing"],
    "product_validation": ["mom_test", "lean_startup", "inspired"],
    "ops_execution": ["four_disciplines", "goal_the", "high_output_management"],
}


def _fallback_for(category: Optional[str], max_lenses: int) -> List[Tuple[int, str, str, str]]:
    """Lens ids for a category, filtered to those that exist in the library."""
    by_id = {i: (i, b, l) for i, b, _, l in _COMPILED}
    out: List[Tuple[int, str, str, str]] = []
    for lens_id in _FALLBACK_LENSES.get(category or "", []):
        if lens_id in by_id:
            i, b, l = by_id[lens_id]
            out.append((0, i, b, l))
        if len(out) >= max_lenses:
            break
    return out


def build_block(message: str, model: Optional[Dict[str, Any]] = None) -> str:
    """The full injected context block, or "" when nothing is relevant.

    An off-topic turn (no category, no scoring lens) returns "" so the prompt stays lean —
    that is the whole reason this is a hook and not a system-prompt section.
    """
    if _env_flag("FORGE_BRAIN_DISABLE"):
        return ""

    category = classify_decision(message)
    # Gate: no decision category means this is not a business-decision turn, so inject nothing.
    # The lens vocabulary is business-domain and would fire wrong frameworks on ordinary agent
    # work ("please" -> 'lease' -> antifragile). The category router is the reliable signal.
    if not category:
        return ""

    spec = _CATEGORIES[category]
    boost_ids = list(spec.get("lenses", []))
    parts: List[str] = [f"DECISION TYPE: {category.replace('_', ' ')}\n{spec['algo']}"]

    chosen = select_lenses(
        message, model=model,
        max_lenses=_env_int("FORGE_BRAIN_MAX_LENSES", 3),
        min_score=_env_int("FORGE_BRAIN_MIN_SCORE", 2),
        boost_ids=boost_ids,
    )
    # A category with no directly-scoring lens still deserves a framework — use the curated
    # fallback set rather than injecting nothing on a high-stakes turn.
    if not chosen:
        chosen = _fallback_for(category, _env_int("FORGE_BRAIN_MAX_LENSES", 3))

    if chosen:
        lines = "\n".join(f"- [{book}] {lens}" for _, _, book, lens in chosen)
        parts.append(
            "REASONING LENSES (from the decision-science knowledge base; the frameworks most "
            "relevant to this turn). Apply them SILENTLY inside your reasoning and weave the "
            "conclusions naturally into your reply. Never lecture, never list frameworks, never "
            "mention 'lenses'; you may credit a thinker by name at most once per reply and only "
            "when it genuinely adds weight:\n" + lines
        )
        if not _env_flag("FORGE_BRAIN_FRUIT_OFF") and os.environ.get("FORGE_BRAIN_FRUIT", "1") != "0":
            fruits = []
            for _, lens_id, book, _ in chosen:
                fp = KNOWLEDGE_MAP.get(lens_id)
                if fp:
                    fruit = load_fruit(fp)
                    if fruit:
                        fruits.append(f'  (rules from "{book}"):\n{fruit}')
            if fruits:
                parts.append("\n\n".join(fruits))

    if not parts:
        return ""

    block = "\n\n".join(parts)
    cap = _env_int("FORGE_BRAIN_MAX_CHARS", 2400)
    if len(block) > cap:
        block = block[:cap].rsplit("\n", 1)[0] + "\n…(truncated)"
    return block


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------

def on_pre_llm_call(user_message: str = "", model: str = "", platform: str = "",
                    **_: Any) -> Optional[Dict[str, str]]:
    """Return {"context": ...} to inject, or None for an untouched turn.

    Hermes joins all valid string / {"context": ...} returns from every subscriber and injects
    them into the user message.
    """
    try:
        block = build_block(user_message, model={"model": model} if model else None)
    except Exception as exc:  # noqa: BLE001 - a hook must never break the agent loop
        logger.warning("forge-brain: build_block failed, injecting nothing: %s", exc)
        return None
    if not block:
        return None
    return {"context": block}


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    logger.info("forge-brain: %d lenses, %d categories wired to pre_llm_call",
                len(MODULES), len(_CATEGORIES))
