"""forge-loop — the autonomous business loop. One cron job that runs the OS.

This is what turns an advisor into an operator. On a schedule it:

  1. READS the state       — queue, metrics ledger, recent actions.
  2. DECIDES               — asks the model what the single highest-leverage move is, given the
                             state, the growth frame, and the business's own numbers.
  3. ACTS                  — executes via the forge-exec tools (idempotent, kernel-gated).
  4. MEASURES              — records a metric datapoint so the next run can see what worked.
  5. REPORTS               — returns a short report; cron delivers it wherever you point it.

Designed to be driven by Hermes cron:

    hermes cron create "every 6h" "Run the forge business loop" --skill forge-business-loop

The skill (`skills/forge-business-loop`) carries the procedure; this module carries the state
helpers the agent calls. The agent is the loop's brain — deliberately, so the reasoning layer
(forge-brain lenses + forge-growth graph) applies to every iteration.

State lives in `$HERMES_HOME/forge-exec/`:
  queue.jsonl    pending business actions
  actions.jsonl  what was done, when, and the outcome
  metrics.jsonl  datapoints over time
  runs.jsonl     one line per loop iteration, with the decision and the delta

Env:
  FORGE_LOOP_DIR      state directory (default: $HERMES_HOME/forge-exec)
  FORGE_LOOP_MAX_ACT  max actions per iteration (default 3) — a loop must not run away
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _dir() -> Path:
    raw = os.environ.get("FORGE_LOOP_DIR", "").strip()
    if raw:
        return Path(raw)
    home = os.environ.get("HERMES_HOME", "").strip()
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "forge-exec"


def _read(name: str, limit: int = 500) -> List[Dict[str, Any]]:
    p = _dir() / f"{name}.jsonl"
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("forge-loop: read %s failed: %s", name, exc)
    return out


def _append(name: str, rec: Dict[str, Any]) -> None:
    try:
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{name}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("forge-loop: append %s failed: %s", name, exc)


def _max_actions() -> int:
    try:
        return max(1, int(os.environ.get("FORGE_LOOP_MAX_ACT", "").strip() or 3))
    except (TypeError, ValueError):
        return 3


# ---------------------------------------------------------------------------
# Tools the loop calls
# ---------------------------------------------------------------------------

def _resolve_queue(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse the append-only queue to the LATEST line per dedupe_key.

    The queue is append-only, so a completion is a new line carrying the same key and a new
    status. Without this collapse the original 'pending' line would still count, and a completed
    action would look permanently pending.
    """
    latest: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for r in rows:
        key = r.get("dedupe_key")
        if not key:
            continue
        if key not in latest:
            order.append(key)
            # the first line for a key carries the action payload
            latest[key] = dict(r)
        else:
            # later lines update status/note but must not erase the payload
            merged = dict(latest[key])
            merged.update({k: v for k, v in r.items() if v is not None})
            latest[key] = merged
    return [latest[k] for k in order]


def forge_loop_state(task_id: Optional[str] = None) -> str:
    """Read the full loop state: queue depth, recent actions, metric trend, last runs.

    This is the FIRST call of every iteration — the loop decides from state, not from memory.
    """
    queue = _resolve_queue(_read("queue", limit=500))
    pending = [r for r in queue if r.get("status") == "pending"]
    actions = _read("actions", limit=200)
    metrics = _read("metrics", limit=500)
    runs = _read("runs", limit=20)

    # Per-metric latest value and delta vs the previous datapoint.
    trend: Dict[str, Dict[str, Any]] = {}
    for m in metrics:
        name = m.get("metric")
        if not name:
            continue
        entry = trend.setdefault(name, {"points": []})
        entry["points"].append(m.get("value"))
    for name, entry in trend.items():
        pts = [p for p in entry["points"] if isinstance(p, (int, float))]
        if pts:
            entry["latest"] = pts[-1]
            entry["previous"] = pts[-2] if len(pts) > 1 else None
            entry["delta"] = round(pts[-1] - pts[-2], 4) if len(pts) > 1 else None
            entry["n"] = len(pts)
        entry.pop("points", None)

    blocked = [a for a in actions if a.get("outcome") == "blocked"]

    return json.dumps({
        "queue": {"pending": len(pending), "entries": pending[-20:]},
        "recent_actions": actions[-20:],
        "blocked_actions": blocked[-5:],
        "metrics": trend,
        "last_runs": runs[-5:],
        "budget": {"max_actions_per_iteration": _max_actions()},
        "state_dir": str(_dir()),
    }, ensure_ascii=False, default=str)


def forge_loop_record_run(decision: str, actions_taken: int, note: str = "",
                          next_check: str = "", task_id: Optional[str] = None) -> str:
    """Close out one iteration: record the decision and what it did.

    Call this LAST. The next iteration reads it, which is how the loop builds a history instead
    of repeating itself.
    """
    rec = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "decision": decision[:1500],
        "actions_taken": int(actions_taken),
        "note": note[:500],
        "next_check": next_check[:200],
    }
    _append("runs", rec)
    return json.dumps({"success": True, "recorded": rec}, ensure_ascii=False)


def forge_loop_complete_action(dedupe_key: str, outcome: str = "done",
                               note: str = "", task_id: Optional[str] = None) -> str:
    """Mark a queued action complete (or failed) by its dedupe_key.

    The queue is append-only, so completion is recorded as a new line carrying the same key;
    `forge_loop_state` treats the LATEST line per key as authoritative.
    """
    queue = _read("queue", limit=2000)
    if not any(r.get("dedupe_key") == dedupe_key for r in queue):
        return json.dumps({"success": False, "reason": "no such dedupe_key"}, ensure_ascii=False)
    _append("queue", {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dedupe_key": dedupe_key,
        "status": outcome,
        "note": note[:500],
    })
    return json.dumps({"success": True, "dedupe_key": dedupe_key, "status": outcome},
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS = [
    ("forge_loop_state", "forge_exec",
     "Read the full business loop state: pending queue, recent actions, metric trends, last runs. "
     "Call this FIRST in every loop iteration — decide from state, not memory.",
     {"type": "object", "properties": {}, "required": []},
     forge_loop_state),

    ("forge_loop_complete_action", "forge_exec",
     "Mark a queued action complete or failed by its dedupe_key",
     {"type": "object", "properties": {
         "dedupe_key": {"type": "string"},
         "outcome": {"type": "string", "description": "done|failed|skipped"},
         "note": {"type": "string"},
     }, "required": ["dedupe_key"]},
     forge_loop_complete_action),

    ("forge_loop_record_run", "forge_exec",
     "Close out a loop iteration: record the decision and what it did. Call this LAST.",
     {"type": "object", "properties": {
         "decision": {"type": "string", "description": "what you decided and why, one short paragraph"},
         "actions_taken": {"type": "integer"},
         "note": {"type": "string"},
         "next_check": {"type": "string", "description": "what the next iteration should look at"},
     }, "required": ["decision", "actions_taken"]},
     forge_loop_record_run),
]


def register(ctx) -> None:
    for name, toolset, description, schema, handler in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset=toolset,
            schema={"name": name, "description": description, "parameters": schema},
            handler=lambda args, _h=handler, **kw: _h(
                **{k: v for k, v in (args or {}).items() if k in _h.__code__.co_varnames},
                task_id=kw.get("task_id"),
            ),
            description=description,
        )
    logger.info("forge-loop: %d tools registered, state at %s", len(_TOOLS), _dir())
