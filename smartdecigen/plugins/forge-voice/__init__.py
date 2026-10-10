"""forge-voice — the operator persona, as a cache-safe system prompt section.

Ported from SmartDecigen's `engine.py` SYSTEM prompt (the voice-bearing sections) and
`journey.py`'s operator framing. This is the CONSTANT part of the persona: it does not change
per turn, so it belongs in a system prompt section, not in a per-turn hook.

Why a section and not a hook: Hermes' prompt-caching invariant forbids rebuilding the system
prompt mid-conversation. A ``register_system_prompt_section`` is rendered ONCE for a new session
and then frozen (and recovered from the persisted prompt after a restart), so it is cache-safe
by construction. Per-turn content (lenses, decision category) rides ``pre_llm_call`` in
forge-brain instead — that is the split.

Constraints from the Hermes contract:
  * ``position="after_memory"`` is the only anchor
  * ``max_chars`` is capped at 4,000 per section; all sections together cap at 8,000
  * the callable runs ONCE per new session — never put per-turn data here

The text is deliberately under the cap: the source SYSTEM prompt is 11,641 chars and about half
of it is a JSON output contract Hermes does not use (Hermes owns the turn loop and its own
response format). What remains is the load-bearing voice: who the operator is, how they speak,
lead-with-value, and the honor-the-request rule that stops a direct request being answered with
a question.

Env:
  FORGE_VOICE_DISABLE=1     do not register the section
  FORGE_VOICE_FILE=<path>   override the persona text with a file
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_SECTION_ID = "forge-voice.operator"
_MAX_CHARS = 4000

# The operator persona — SmartDecigen's engine.py voice sections, assembled verbatim.
# Kept as one constant so it is inspectable and diffable; the file override exists for users
# who want their own voice without editing code.
PERSONA = """You are a sharp operator who has done this before. Not a coach, not a therapist, not a chatbot.

WHO YOU ARE:
- You care about outcomes, not comfort in the moment. Warm because you are invested, not because you are polite.
- You give real, specific observations. When you lack data, say so plainly and give your best read.
- You stay honest about reality even when it is unwelcome. Agree because it is right, not because it was said.

THE WAY YOU SPEAK:
- Plain English. Short sentences. One idea at a time.
- Concrete over generic. Numbers over adjectives.
- No filler, no corporate speak, no emojis, no exclamation marks.
- Contractions welcome. Every line earns its place.

LEAD WITH VALUE: open every reply with ONE punchy, genuinely useful line — the single most valuable
thing this turn (a direct answer, a number, a sharp recommendation, the key first step, a warning, or
a reframe). Not always a number; pick the value type that fits.

HONOR THE REQUEST: if asked for a plan, an answer, a draft, or a list, or asked to suggest /
recommend / pick / choose, DELIVER the full thing now. When asked to recommend, COMMIT to ONE
specific, named option — never a category or a menu: name it, justify it in one line, give the first
move. NEVER answer a direct request by asking a question instead.

PREDICT THE OUTCOME: when you recommend an action or a plan, commit to ONE measurable prediction
(what will happen, roughly when, and the number that proves it). If you cannot predict it, say why.

STATE WHAT WOULD CHANGE YOUR MIND: every recommendation carries the condition that would flip it.
A recommendation without a falsifier is an opinion."""


def _persona() -> str:
    """The persona text: a file override if configured, else the built-in constant."""
    override = os.environ.get("FORGE_VOICE_FILE", "").strip()
    if override:
        try:
            text = Path(override).read_text(encoding="utf-8").strip()
            if text:
                return text
            logger.warning("forge-voice: %s is empty, using built-in persona", override)
        except Exception as exc:  # noqa: BLE001
            logger.warning("forge-voice: cannot read %s (%s), using built-in persona", override, exc)
    return PERSONA


def build_section(session_info=None) -> str:
    """Render the section. Called once per new session by Hermes.

    ``session_info`` is a read-only mapping (session_id, model, provider, platform,
    profile_name, cwd). Nothing here varies by session, but the parameter is accepted because
    Hermes passes it.
    """
    if os.environ.get("FORGE_VOICE_DISABLE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return ""
    text = _persona()
    if len(text) > _MAX_CHARS:
        # Never let Hermes drop the section for being oversized — trim and say so.
        logger.warning("forge-voice: persona is %d chars, trimming to %d", len(text), _MAX_CHARS)
        text = text[:_MAX_CHARS].rsplit("\n", 1)[0]
    return text


def register(ctx) -> None:
    ctx.register_system_prompt_section(
        _SECTION_ID,
        build_section,
        position="after_memory",
        max_chars=_MAX_CHARS,
    )
    logger.info("forge-voice: operator persona registered (%d chars)", len(_persona()))
