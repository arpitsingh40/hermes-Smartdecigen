"""forge-confirm — a final quality gate on the reply, via transform_llm_output.

Ported from SmartDecigen's `engine.py::_confirm_final_reply` + `CONFIRM_SYSTEM`. Runs one
host-owned LLM call after the agent has produced its reply, checks that the reply actually
answers what was asked, and rewrites it for connection if it does not.

TWO HOOKS, AND WHY
------------------
`transform_llm_output` carries only `response_text, session_id, model, platform, turn_id` — it
does NOT carry the user's message, and the plugin context exposes no accessor for it (verified in
`agent/turn_finalizer.py::apply_llm_output_transform`). Step 1 of the gate ("does this answer
what was asked?") is impossible without the question.

So this plugin registers BOTH hooks:

  pre_llm_call          fires first in the turn and carries `user_message`. Stash it, keyed by
                        session, with a TTL and LRU bound.
  transform_llm_output  fires last and carries the draft. Read the stashed message, run the gate.

Without the stash the gate either never runs or rewrites blind — the latter being the exact
failure the gate exists to prevent. (An earlier version of this plugin had no stash and therefore
could never fire at all.)

COST: one extra LLM call per turn. Real money, so OFF by default (FORGE_CONFIRM=1). The disabled
path returns before any call.

WHY IT FAILS OPEN, UNLIKE THE GOVERNANCE GATE
The governance gate (ari-governance) fails CLOSED because it guards money — an unreachable gate
must not permit spend. This gate guards prose. If the model call fails, times out, or returns
something unparseable, the draft reply is already good enough to ship; blocking or blanking it
would be strictly worse. So every failure path here returns None (keep the draft).

Env:
  FORGE_CONFIRM=1           enable the gate (default: off)
  FORGE_CONFIRM_MAX_TOKENS  token cap for the confirm call (default 1600)
  FORGE_CONFIRM_TTL         seconds a stashed message stays valid (default 900)
  FORGE_CONFIRM_STASH_MAX   max concurrent sessions stashed (default 64)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}

# The quality gate prompt — SmartDecigen's CONFIRM_SYSTEM, kept verbatim in substance.
CONFIRM_INSTRUCTIONS = """You are the final quality gate for an operator's assistant. A draft reply has been written.
Your ONLY job: make it undeniable.

Step 1 — TRUE REPLY CHECK. Read the user's message. Does the draft genuinely answer what they
actually asked? If it dodges, generalizes, or answers a different question, the draft FAILS.

Step 2 — BEST POSSIBLE CHECK. Is this the best reply they could receive right now? The best reply
is sharp, concrete, specific to their situation, free of fluff, and gives them something they can
act on. If there is any generic filler or weak phrasing, improve it.

Step 3 — REWRITE FOR CONNECTION. Trust is FELT in the tone, never stated. Rewrite so the voice is
warm, direct, a little magnetic. Simple powerful sentences.

STRICT RULES:
- Keep facts, numbers, and specifics from the draft exactly as they are. Only upgrade tone and
  sharpness. Never invent a fact that is not in the draft.
- Never use the word "friend". Never say "I'm on your side", "I've got your back",
  "we're in this together", "I'm in your corner", "you can count on me", "trust me".
- End in a way that leaves them feeling capable.
- If the draft already passes all three checks, return it nearly verbatim with verdict "kept".
"""

CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["kept", "improved"]},
        "reply": {"type": "string"},
    },
    "required": ["verdict", "reply"],
}

# Above this the draft is already long; rewriting it risks more than it gains and costs more.
_MAX_DRAFT_CHARS = 8000


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Message stash — the bridge between the two hooks
# ---------------------------------------------------------------------------

class MessageStash:
    """Bounded, TTL'd, thread-safe map of session -> (user_message, monotonic_ts).

    Keyed by session_id, falling back to task_id then a single-slot key, so a session-less
    surface still works. OrderedDict gives LRU eviction with no extra bookkeeping.
    """

    def __init__(self, max_entries: int = 64, ttl_seconds: float = 900.0):
        self._lock = threading.Lock()
        self._data: "OrderedDict[str, Tuple[str, float]]" = OrderedDict()
        self._max = max(1, max_entries)
        self._ttl = max(1.0, ttl_seconds)

    def put(self, key: str, message: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._data[key] = (message, now)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def get(self, key: str) -> str:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return ""
            message, ts = entry
            if now - ts > self._ttl:
                del self._data[key]
                return ""
            self._data.move_to_end(key)
            return message

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


_STASH = MessageStash(
    max_entries=_env_int("FORGE_CONFIRM_STASH_MAX", 64),
    ttl_seconds=float(_env_int("FORGE_CONFIRM_TTL", 900)),
)


def _stash_key(session_id: str, task_id: str = "") -> str:
    return session_id or task_id or "_default"


# ---------------------------------------------------------------------------
# Pre-checks (cheap — run before any LLM call)
# ---------------------------------------------------------------------------

def should_check(draft: str, user_message: str) -> bool:
    """Cheap pre-checks before spending an LLM call."""
    if not _env_flag("FORGE_CONFIRM"):
        return False
    if not draft or not draft.strip():
        return False
    if len(draft) > _MAX_DRAFT_CHARS:
        return False
    if not user_message or not user_message.strip():
        return False
    # Nothing to confirm on a pure tool-status line or a one-word acknowledgement.
    if len(draft.strip()) < 40:
        return False
    return True


def build_prompt(draft: str, user_message: str) -> str:
    return (
        f"USER'S MESSAGE:\n{user_message.strip()}\n\n"
        f"DRAFT REPLY TO CONFIRM:\n{draft.strip()}\n\n"
        "Run the three checks now and output the verdict plus the final reply."
    )


def on_pre_llm_call(user_message: str = "", session_id: str = "", task_id: str = "",
                    **_: Any) -> None:
    """Stash this turn's user message so the transform hook can see it. Observer — returns None."""
    try:
        if user_message:
            _STASH.put(_stash_key(session_id, task_id), user_message)
    except Exception as exc:  # noqa: BLE001 - never break the turn
        logger.debug("forge-confirm: stash failed: %s", exc)
    return None


def on_transform_llm_output(response_text: str = "", session_id: str = "",
                            task_id: str = "", **_: Any) -> Optional[str]:
    """Run the gate. Returns the improved reply, or None to keep the draft."""
    try:
        user_message = _STASH.get(_stash_key(session_id, task_id))
        return run_gate(response_text, user_message)
    except Exception as exc:  # noqa: BLE001 - a hook must never break delivery
        logger.warning("forge-confirm: gate error, keeping draft: %s", exc)
        return None


# The live plugin context, bound at register(). The transform hook needs ctx.llm; holding the
# reference is simpler than threading it through a hook signature Hermes controls.
_CTX: Any = None


def register(ctx) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
    logger.info("forge-confirm: registered (%s)",
                "enabled" if _env_flag("FORGE_CONFIRM") else "disabled — set FORGE_CONFIRM=1")


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def run_gate(response_text: str, user_message: str, ctx: Any = None) -> Optional[str]:
    """One structured LLM call. Returns the improved reply, or None to keep the draft."""
    if not should_check(response_text, user_message):
        return None
    ctx = ctx if ctx is not None else _CTX
    if ctx is None:
        logger.debug("forge-confirm: no ctx bound, skipping")
        return None

    result = ctx.llm.complete_structured(
        instructions=CONFIRM_INSTRUCTIONS,
        input=[{"type": "text", "text": build_prompt(response_text, user_message)}],
        json_schema=CONFIRM_SCHEMA,
        purpose="forge.confirm",
        temperature=0.2,
        max_tokens=_env_int("FORGE_CONFIRM_MAX_TOKENS", 1600),
    )

    parsed = getattr(result, "parsed", None)
    if not isinstance(parsed, dict):
        logger.debug("forge-confirm: unparsed response, keeping draft")
        return None

    final = (parsed.get("reply") or "").strip()
    if not final or final == response_text.strip():
        return None  # "kept" — no change, return None so Hermes skips the replacement
    logger.info("forge-confirm: verdict=%s, reply rewritten (%d -> %d chars)",
                parsed.get("verdict"), len(response_text), len(final))
    return final
