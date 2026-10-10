"""forge-growth — the business graph, root-cause walker, opportunity scanner, and 10× planner.

Ported from SmartDecigen's `business_system.py` (627 lines) and `growth_engine.py` (75 lines).
This is the layer that turns "we have a problem" into "here is the function that is actually
broken, here is what usually causes it, and here is the move that compounds."

Three things it does, all on `pre_llm_call`:

  1. SYMPTOM DETECTION + ROOT-CAUSE WALK. A regex scan maps the message to one of 16 business
     functions ("revenue is dropping" -> sales). The walker then traverses the dependency graph
     UPSTREAM (sales depends on marketing + product) to depth 2, so the reply addresses the
     cause rather than the symptom.

  2. OPPORTUNITY SCAN. Pattern-matches the message against the knowledge base's growth patterns
     (adjacent market, under-served channel, platform play, partnership distribution) so a
     "how do we grow" turn gets a concrete avenue, not a platitude.

  3. 10× PLANNER. On an explicit growth-plan request, injects the planning frame: 12-month
     target, named loops with cadence and metric, milestones with proof. The frame is injected;
     the model fills it against the actual business.

Why `pre_llm_call` and not a system prompt section: the content is per-turn and variable.
Hermes' caching invariant forbids changing the system prompt mid-conversation, and this rides
the user message instead.

Design notes carried from the source and one deliberate change:

* The symptom regexes are ALREADY word-bounded and phrase-based in the source (`\b(revenue|sales)
  .*(dropping|declining...)`), so they do not have the substring weakness the lens vocabulary
  had. Kept verbatim.
* The dependency graph is directional: `DEPENDENCY_GRAPH[f]` lists what f depends on, so the walk
  goes upstream through those edges. `leadership` is a valid symptom target with no graph node —
  handled explicitly.
* No org state is required. The source's walker read health scores from MongoDB; here the graph
  supplies the STRUCTURE and the message supplies the symptom, so the walk is useful without a
  database. Health scores are an optional enrichment (`FORGE_GROWTH_HEALTH`), not a dependency.

Env:
  FORGE_GROWTH_DISABLE=1     inject nothing
  FORGE_GROWTH_MAX_CHARS     hard cap on the injected block (default 2000)
  FORGE_GROWTH_DEPTH         root-cause walk depth (default 2)
  FORGE_GROWTH_HEALTH        JSON dict of function -> health (0-100); optional enrichment
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
# Data (loaded once at import)
# ---------------------------------------------------------------------------

def _load_json(name: str) -> Dict[str, Any]:
    try:
        with open(_BASE / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.error("forge-growth: cannot load %s: %s", name, exc)
        return {}


_D = _load_json("graph.json")

DEPENDENCY_GRAPH: Dict[str, List[str]] = _D.get("dependency_graph", {})
FUNCTION_LABELS: Dict[str, str] = _D.get("function_labels", {})
OPPORTUNITY_PATTERNS: Dict[str, List[Dict[str, str]]] = _D.get("opportunity_patterns", {})
FAILURE_MODES: Dict[str, List[Dict[str, str]]] = _D.get("failure_modes", {})

# Compile the symptom patterns once — they run on every turn.
_SYMPTOMS: Tuple[Tuple[Any, str], ...] = tuple(
    (re.compile(pat, re.IGNORECASE), func)
    for pat, func in _D.get("symptom_patterns", [])
)

# "leadership" is a valid symptom target but not a graph node (the founder is not a function).
_EXTRA_LABELS = {"leadership": "Founder & Leadership"}


def label(func: str) -> str:
    return FUNCTION_LABELS.get(func) or _EXTRA_LABELS.get(func) or func.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Symptom detection
# ---------------------------------------------------------------------------

def detect_symptoms(message: str) -> List[str]:
    """Map a message to affected business functions. Max 3, to bound context cost.

    Ported from business_system.py::detect_symptoms — the patterns are already word-bounded
    and phrase-based, so no matcher change is needed.
    """
    if not message:
        return []
    detected: List[str] = []
    for rx, func in _SYMPTOMS:
        if rx.search(message):
            if func not in detected:
                detected.append(func)
    return detected[:3]


# ---------------------------------------------------------------------------
# Root-cause walk
# ---------------------------------------------------------------------------

def _health(func: str) -> Optional[int]:
    raw = os.environ.get("FORGE_GROWTH_HEALTH", "").strip()
    if not raw:
        return None
    try:
        table = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    value = table.get(func)
    return int(value) if isinstance(value, (int, float)) else None


def build_tree(func: str, depth: int = 0, max_depth: int = 2,
               path: Optional[frozenset] = None) -> Dict[str, Any]:
    """Walk UPSTREAM: what does this function depend on, and what does that depend on.

    The dependency graph lists a function's upstream dependencies, so a broken function is
    usually a symptom of something further up. Bounded depth prevents runaway recursion.

    ``path`` is the chain of ancestors on THIS branch, used for cycle detection. It must be the
    path, not a global visited-set: a function reachable by two routes (product is reachable via
    both marketing and sales) has to appear on both, or the tree silently drops real dependencies.
    """
    path = path or frozenset()
    if func in path or depth > max_depth:
        return {}
    path = path | {func}

    node: Dict[str, Any] = {
        "function": func,
        "label": label(func),
        "depends_on": DEPENDENCY_GRAPH.get(func, []),
    }
    health = _health(func)
    if health is not None:
        node["health"] = health
        node["status"] = "healthy" if health >= 70 else ("warning" if health >= 50 else "at_risk")
    modes = FAILURE_MODES.get(func, [])
    if modes:
        node["common_failures"] = [m["failure"] for m in modes[:2]]

    children = [
        build_tree(dep, depth + 1, max_depth, path)
        for dep in DEPENDENCY_GRAPH.get(func, [])
    ]
    node["upstream"] = [c for c in children if c]
    return node


def format_tree(node: Dict[str, Any], indent: int = 0) -> str:
    """Compact text rendering for the prompt."""
    if not node:
        return ""
    pad = "  " * indent
    health = f", health {node['health']}/100 ({node['status']})" if "health" in node else ""
    lines = [f"{pad}- {node['label']}{health}"]
    if node.get("common_failures"):
        lines.append(f"{pad}  usual causes: {'; '.join(node['common_failures'])}")
    for child in node.get("upstream", []):
        lines.append(format_tree(child, indent + 1))
    return "\n".join(lines)


def root_cause_block(message: str, max_depth: int = 2) -> str:
    """Detect symptoms, walk upstream, render. Empty string when nothing is detected."""
    symptoms = detect_symptoms(message)
    if not symptoms:
        return ""
    parts: List[str] = []
    for func in symptoms[:2]:  # max 2 walks to bound tokens
        tree = build_tree(func, max_depth=max_depth)
        if tree:
            parts.append(format_tree(tree))
    if not parts:
        return ""
    return (
        "ROOT CAUSE (auto-detected from the message — act on this analysis, do not narrate the "
        "detection). The tree reads outward from the symptom to what it depends on, so the "
        "deeper node is usually the real constraint:\n" + "\n\n".join(parts)
    )


# ---------------------------------------------------------------------------
# Opportunity scan
# ---------------------------------------------------------------------------

_GROWTH_ASK = re.compile(
    r"\b(grow|growth|scale|scaling|10x|10 ?x|double|triple|expand|expansion|next (level|stage)|"
    r"more (revenue|customers|sales)|increase (revenue|sales)|new (market|channel|segment))\b",
    re.IGNORECASE,
)


def wants_growth(message: str) -> bool:
    return bool(_GROWTH_ASK.search(message or ""))


def opportunity_block(message: str) -> str:
    """Surface growth avenues for the functions the message touches.

    If the message names no function, use the growth-relevant defaults — a generic "how do we
    grow" turn should still get real avenues rather than nothing.
    """
    funcs = detect_symptoms(message)
    if not funcs:
        funcs = ["growth", "marketing", "sales", "product"]
    # growth isn't a key in the pattern table; its avenues come from marketing/sales/product.
    candidates = [f for f in funcs if f in OPPORTUNITY_PATTERNS]
    for fallback in ("marketing", "sales", "product", "strategy"):
        if len(candidates) >= 2:
            break
        if fallback in OPPORTUNITY_PATTERNS and fallback not in candidates:
            candidates.append(fallback)
    if not candidates:
        return ""

    lines: List[str] = []
    for func in candidates[:2]:
        for pat in OPPORTUNITY_PATTERNS.get(func, [])[:2]:
            lines.append(f"- [{label(func)}] {pat['pattern']}  (from {pat['source']})")
    if not lines:
        return ""
    return (
        "GROWTH AVENUES (patterns matched to this business's situation — pick the one with the "
        "shortest path to evidence, and name the first test):\n" + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# 10× planner frame
# ---------------------------------------------------------------------------

PLANNER_FRAME = """10x GROWTH PLAN — required shape:
- 12-month target stated as one number (revenue, or orders if pre-revenue).
- 2-4 LOOPS, each: name, cadence (daily/weekly/continuous), owner, the 2-3 moves it runs, and
  the ONE metric it moves. A loop is a repeating system, not a one-off task.
- Milestones at month 1 / 3 / 6 / 12, each with a target AND the proof that shows it landed.
- Lean constraint: a 2-5 person team plus AI. If a step needs a 20-person org, cut it.
- Every lever either maps to a tool the agent can call, or is explicitly marked MANUAL.
- Compounding check: say which loop feeds which. Independent loops are a to-do list; feeding
  loops are a growth engine. If none feed each other, say so plainly — that is the finding."""


def growth_plan_block(message: str) -> str:
    if not wants_growth(message):
        return ""
    return PLANNER_FRAME


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n…(truncated)"


def build_block(message: str) -> str:
    if _env_flag("FORGE_GROWTH_DISABLE") or not message:
        return ""

    depth = _env_int("FORGE_GROWTH_DEPTH", 2)
    rc = root_cause_block(message, max_depth=depth)
    growth_ask = wants_growth(message)

    # Order matters, because the total cap truncates the tail. A growth request wants the plan
    # and the avenues FIRST — those are the deliverable. A plain problem turn wants the
    # diagnosis first. The root-cause tree is the most verbose section, so it goes last on a
    # growth turn where the plan would otherwise be starved.
    parts: List[str] = []
    if growth_ask:
        parts.append(_trim(growth_plan_block(message), 900))
        parts.append(_trim(opportunity_block(message), 600))
        if rc:
            parts.append(_trim(rc, 900))
    else:
        if rc:
            parts.append(_trim(rc, 1100))
        if detect_symptoms(message):
            # A problem turn benefits from an avenue, but the plan frame would be noise.
            parts.append(_trim(opportunity_block(message), 600))

    parts = [p for p in parts if p]
    if not parts:
        return ""

    block = "\n\n".join(parts)
    cap = _env_int("FORGE_GROWTH_MAX_CHARS", 2000)
    return _trim(block, cap)


def on_pre_llm_call(user_message: str = "", **_: Any) -> Optional[Dict[str, str]]:
    try:
        block = build_block(user_message)
    except Exception as exc:  # noqa: BLE001 - a hook must never break the turn
        logger.warning("forge-growth: build_block failed: %s", exc)
        return None
    if not block:
        return None
    return {"context": block}


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    logger.info("forge-growth: %d functions, %d symptom patterns wired to pre_llm_call",
                len(DEPENDENCY_GRAPH), len(_SYMPTOMS))
