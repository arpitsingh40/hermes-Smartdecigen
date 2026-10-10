"""ari-governance — gate Hermes tool calls through the ARI kernel before they execute.

The kernel (Rust/Postgres) owns spend caps, kill switches, tenant isolation and the audit
trail. Hermes owns the tool loop. This plugin is the seam: it asks the kernel "may this org
spend this much on this action, right now?" and blocks the tool when the answer is no.

Two hooks, in opposite directions:

  pre_tool_call          money-moving tools are gated. Kernel says blocked/dry_run -> the tool
                         does not run. **Fail-closed**: if the kernel is unreachable, the tool
                         is blocked, because an unreachable money gate must not fail open.
  post_tool_call         on a successful gated tool, the actual cost is committed to the
                         kernel's weekly bucket (POST /api/v1/spend) exactly once.

Design notes that matter:

* Fail-closed is opt-outable per action class. Read-only and local tools (read_file, search_files,
  terminal) never reach the kernel — gating them would put a network round-trip on every turn and
  make the agent useless when the kernel is down. Only tools in ``GATED_ACTIONS`` (or matched by
  ``EXTRA_GATED_TOOLS``) are gated. Widen the set, don't gate everything.
* The kernel's ``/api/v1/gate`` is a pure read: it audits but does not move the spend bucket.
  Spend is committed on success in ``post_tool_call``, so a blocked-then-retried call cannot
  double-count.
* A missing JWT or org id is a configuration error, not an allow. The gate blocks with a message
  the model can read and relay to the operator.

Environment:
  ARI_KERNEL_URL       base URL of the kernel (default http://127.0.0.1:8080)
  ARI_JWT              bearer token for the org (required to gate anything)
  ARI_ORG_ID           org id to gate against; defaults to the token's org if unset
  ARI_GATE_TIMEOUT     seconds to wait on the kernel (default 5; hook cap is 30)
  ARI_GATE_DISABLE=1   kill switch — pass everything through (use only for local dev)
  ARI_GATE_FAIL_OPEN=1 dangerous: allow tools when the kernel is unreachable. Never in prod.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_KERNEL_URL = "http://127.0.0.1:8080"
_DEFAULT_TIMEOUT = 5.0

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _kernel_url() -> str:
    return os.environ.get("ARI_KERNEL_URL", _DEFAULT_KERNEL_URL).rstrip("/")


def _timeout() -> float:
    try:
        return float(os.environ.get("ARI_GATE_TIMEOUT", _DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# Which tool calls cost money, and how much
# ---------------------------------------------------------------------------

# tool_name -> (action label sent to the kernel, estimated cost in USD).
# Only these are gated. Anything not listed passes through untouched.
GATED_ACTIONS: Dict[str, tuple[str, float]] = {
    "send_email": ("email.send", 0.01),
    "email_send": ("email.send", 0.01),
    "send_message": ("message.send", 0.01),
    "image_generate": ("image.generate", 0.04),
    "video_generate": ("video.generate", 0.50),
    "text_to_speech": ("tts.generate", 0.02),
    "browser_exec": ("browser.session", 0.02),
    "computer_use": ("computer.session", 0.05),
    "deploy": ("deploy.run", 0.10),
}

# Extra tool names to gate, comma-separated, for orgs with custom tools.
# Each gets a flat 0.01 estimate unless the name also appears in GATED_ACTIONS.
_EXTRA_ENV = "ARI_GATE_EXTRA_TOOLS"


def gated_actions() -> Dict[str, tuple[str, float]]:
    """The effective gate table: built-ins plus any org-configured extras."""
    table = dict(GATED_ACTIONS)
    for raw in os.environ.get(_EXTRA_ENV, "").split(","):
        name = raw.strip()
        if name and name not in table:
            table[name] = (name, 0.01)
    return table


def should_gate(tool_name: str) -> Optional[tuple[str, float]]:
    """Return ``(action, estimated_cost)`` if this tool is gated, else None."""
    if not tool_name:
        return None
    return gated_actions().get(tool_name)


# ---------------------------------------------------------------------------
# The kernel call
# ---------------------------------------------------------------------------

def _kernel_headers() -> Optional[Dict[str, str]]:
    jwt = os.environ.get("ARI_JWT", "").strip()
    if not jwt:
        return None
    return {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}


def _org_id() -> Optional[str]:
    org = os.environ.get("ARI_ORG_ID", "").strip()
    return org or None


def ask_kernel(action: str, cost: float, agent_id: str, trace_id: Optional[str]) -> Dict[str, Any]:
    """POST /api/v1/gate. Returns the parsed verdict.

    Raises on transport failure so the caller can apply its fail-closed policy explicitly —
    this function never silently converts an error into an allow.
    """
    import httpx  # Hermes ships httpx as a direct dependency

    headers = _kernel_headers()
    if headers is None:
        raise RuntimeError("ARI_JWT is not set — cannot reach the kernel")
    org = _org_id()
    if org is None:
        raise RuntimeError("ARI_ORG_ID is not set — cannot gate against an org")

    body = {
        "org_id": org,
        "agent_id": agent_id or "hermes",
        "action": action,
        "estimated_cost_usd": cost,
        "trace_id": trace_id,
    }
    resp = httpx.post(f"{_kernel_url()}/api/v1/gate", json=body, headers=headers, timeout=_timeout())
    resp.raise_for_status()
    return resp.json()


def commit_spend(action: str, cost: float, agent_id: str, trace_id: Optional[str]) -> None:
    """POST /api/v1/spend after a gated tool succeeded. Best-effort: a failure here is logged,
    not raised, because the tool already ran and blocking now would be a lie."""
    import httpx

    headers = _kernel_headers()
    org = _org_id()
    if headers is None or org is None:
        logger.warning("ari-governance: cannot commit spend (%s) — ARI_JWT/ARI_ORG_ID unset", action)
        return
    body = {
        "org_id": org,
        "agent_id": agent_id or "hermes",
        "action": action,
        "amount_usd": cost,
        "trace_id": trace_id,
    }
    try:
        httpx.post(f"{_kernel_url()}/api/v1/spend", json=body, headers=headers, timeout=_timeout())
    except Exception as exc:  # noqa: BLE001 - spend commit must never break the turn
        logger.warning("ari-governance: spend commit failed for %s: %s", action, exc)


# ---------------------------------------------------------------------------
# Hook: pre_tool_call — the gate
# ---------------------------------------------------------------------------

def _block(message: str) -> Dict[str, str]:
    return {"action": "block", "message": message}


def _gate_verdict(tool_name: str, args: Any, task_id: str = "", session_id: str = "", **_: Any):
    """Pure-ish core of the gate, separated so the decision logic is unit-testable without
    monkeypatching the module-level httpx call. Returns a hook return value or None."""
    if _env_flag("ARI_GATE_DISABLE"):
        return None

    spec = should_gate(tool_name)
    if spec is None:
        return None  # not a money-moving tool — pass through

    action, cost = spec
    trace_id = session_id or task_id or None

    try:
        verdict = ask_kernel(action, cost, agent_id=tool_name, trace_id=trace_id)
    except Exception as exc:  # noqa: BLE001
        if _env_flag("ARI_GATE_FAIL_OPEN"):
            logger.error("ari-governance: kernel unreachable, FAIL-OPEN per env: %s", exc)
            return None
        # Fail closed: an unreachable money gate must not let spend through.
        return _block(
            f"ari-governance blocked `{tool_name}`: the governance kernel at {_kernel_url()} "
            f"could not be reached ({exc}). This is a fail-closed gate — no spend was authorised. "
            f"Start the kernel, or set ARI_GATE_FAIL_OPEN=1 to override (development only)."
        )

    gate = (verdict or {}).get("gate")
    if gate == "allowed":
        return None

    reason = (verdict or {}).get("reason") or "no reason supplied"
    used = (verdict or {}).get("weekly_spend_used_usd")
    cap = (verdict or {}).get("weekly_spend_cap_usd")
    budget = f" (weekly spend ${used:.2f} / cap ${cap:.2f})" if isinstance(used, (int, float)) and isinstance(cap, (int, float)) else ""

    if gate == "dry_run":
        return _block(
            f"ari-governance: `{tool_name}` is in DRY-RUN for this org — {reason}{budget}. "
            f"The action was audited but not executed."
        )
    if gate == "blocked":
        return _block(
            f"ari-governance blocked `{tool_name}` ({action}): {reason}{budget}. "
            f"Raise the org's weekly cap or resolve the approval to proceed."
        )
    # Unknown verdict from a newer kernel: fail closed.
    return _block(
        f"ari-governance blocked `{tool_name}`: unrecognised kernel verdict {gate!r}. "
        f"Failing closed because the gate could not be interpreted."
    )


def on_pre_tool_call(tool_name: str = "", args: Any = None, task_id: str = "", session_id: str = "", **kwargs: Any):
    try:
        return _gate_verdict(tool_name, args, task_id=task_id, session_id=session_id, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a hook must never crash the agent loop
        logger.warning("ari-governance: gate error, passing through: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Hook: post_tool_call — commit the spend
# ---------------------------------------------------------------------------

def on_post_tool_call(tool_name: str = "", args: Any = None, result: Any = None,
                      task_id: str = "", session_id: str = "", **_: Any) -> None:
    """After a gated tool succeeded, commit its cost. Observers return nothing."""
    if _env_flag("ARI_GATE_DISABLE"):
        return
    spec = should_gate(tool_name)
    if spec is None:
        return

    # Only commit when the tool actually succeeded. Hermes passes the raw result string;
    # treat an error-shaped result as "no spend".
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and parsed.get("error"):
                return
        except (ValueError, TypeError):
            pass

    action, cost = spec
    commit_spend(action, cost, agent_id=tool_name, trace_id=session_id or task_id or None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    logger.info("ari-governance: gate wired to %s (fail-closed)", _kernel_url())
