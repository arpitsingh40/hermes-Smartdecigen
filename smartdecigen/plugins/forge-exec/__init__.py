"""forge-exec — the execution layer. Business actions, gated by the kernel.

This is the piece the stack was missing. Everything else reasons, diagnoses, or plans; nothing
acted. This plugin registers the tools that DO things, and every one of them is:

  1. **Idempotent** — each action takes a `dedupe_key`; a repeat with the same key is a no-op.
     A cron loop that fires twice must not email the customer twice.
  2. **Kernel-gated** — money-moving actions ask the governance kernel before executing. If the
     kernel is unreachable the action is refused (fail closed), same policy as ari-governance.
  3. **Audited** — every action appends a line to a local JSONL ledger, so the loop leaves a
     trail even when the kernel is not running.
  4. **Dry-run by default** — with FORGE_EXEC_LIVE unset, actions are recorded and returned as
     "would have done X" instead of being performed. Turning on live execution is an explicit,
     deliberate act.

The tools
---------
  forge_log_action      record an action taken (always available, no side effect)
  forge_queue_action    enqueue a business action for the loop to process
  forge_list_queue      read the queue
  forge_send_message    send a message (email/whatsapp/slack) — SIDE EFFECT, kernel-gated
  forge_record_metric   append a metric datapoint to the local metrics ledger

Why a tool and not a hook: these are capabilities the model CHOOSES to call. A hook fires
whether or not it should; a tool is the agent deciding.

Env:
  FORGE_EXEC_LIVE=1        actually perform side effects (default: dry-run)
  FORGE_EXEC_DIR           ledger directory (default: $HERMES_HOME/forge-exec)
  FORGE_EXEC_KERNEL_URL    kernel base URL (default: http://127.0.0.1:8080)
  FORGE_EXEC_JWT           bearer token for the kernel
  FORGE_EXEC_ORG_ID        org id to gate against
  FORGE_EXEC_FAIL_OPEN=1   allow side effects when the kernel is unreachable. NEVER in prod.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_KERNEL = "http://127.0.0.1:8080"

# Actions that move money or touch a customer. These are kernel-gated.
_MONEY_ACTIONS = {"send_message", "send_campaign", "charge", "refund", "spend_ads", "deploy"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def ledger_dir() -> Path:
    raw = os.environ.get("FORGE_EXEC_DIR", "").strip()
    if raw:
        return Path(raw)
    home = os.environ.get("HERMES_HOME", "").strip()
    base = Path(home) if home else Path.home() / ".hermes"
    return base / "forge-exec"


def _append(name: str, record: Dict[str, Any]) -> Path:
    """Append one JSON line to a ledger file. Creates the dir. Never raises."""
    d = ledger_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{name}.jsonl"
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return p
    except Exception as exc:  # noqa: BLE001 - the ledger must never break an action
        logger.warning("forge-exec: ledger append failed (%s): %s", name, exc)
        return d / f"{name}.jsonl"


def _read_jsonl(name: str, limit: int = 200) -> List[Dict[str, Any]]:
    p = ledger_dir() / f"{name}.jsonl"
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("forge-exec: ledger read failed (%s): %s", name, exc)
    return out


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def _seen_keys(name: str = "actions") -> set:
    return {r.get("dedupe_key") for r in _read_jsonl(name, limit=2000) if r.get("dedupe_key")}


def _make_key(action: str, target: str, body: str) -> str:
    h = hashlib.sha256(f"{action}|{target}|{body}".encode("utf-8", "replace")).hexdigest()[:16]
    return h


# ---------------------------------------------------------------------------
# Kernel gate
# ---------------------------------------------------------------------------

def _kernel_gate(action: str, estimated_cost: float, trace_id: str = "") -> Dict[str, Any]:
    """Ask the kernel whether this action may run. Returns {allowed, verdict, reason}.

    Fail CLOSED: if the kernel is unreachable and FORGE_EXEC_FAIL_OPEN is not set, refuse.
    """
    if action not in _MONEY_ACTIONS:
        return {"allowed": True, "verdict": "ungated", "reason": ""}

    if _env_flag("FORGE_EXEC_FAIL_OPEN"):
        pass  # fall through to the call; on failure we allow

    url = os.environ.get("FORGE_EXEC_KERNEL_URL", _DEFAULT_KERNEL).rstrip("/")
    jwt = os.environ.get("FORGE_EXEC_JWT", "").strip()
    org = os.environ.get("FORGE_EXEC_ORG_ID", "").strip()

    if not jwt or not org:
        if _env_flag("FORGE_EXEC_FAIL_OPEN"):
            return {"allowed": True, "verdict": "ungated", "reason": "no kernel credentials"}
        return {"allowed": False, "verdict": "blocked",
                "reason": "kernel credentials not configured (FORGE_EXEC_JWT / FORGE_EXEC_ORG_ID)"}

    try:
        import httpx
        resp = httpx.post(
            f"{url}/api/v1/gate",
            json={"org_id": org, "agent_id": "forge-exec", "action": action,
                  "estimated_cost_usd": estimated_cost, "trace_id": trace_id or None},
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        if _env_flag("FORGE_EXEC_FAIL_OPEN"):
            return {"allowed": True, "verdict": "ungated", "reason": f"kernel unreachable: {exc}"}
        return {"allowed": False, "verdict": "blocked",
                "reason": f"governance kernel unreachable ({exc}) — failing closed"}

    verdict = (data or {}).get("gate", "blocked")
    if verdict == "allowed":
        return {"allowed": True, "verdict": verdict, "reason": ""}
    return {"allowed": False, "verdict": verdict,
            "reason": (data or {}).get("reason") or f"kernel verdict: {verdict}"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def forge_log_action(action: str, target: str = "", detail: str = "",
                     outcome: str = "done", dedupe_key: str = "", task_id: Optional[str] = None) -> str:
    """Record an action that was taken. Always safe — no side effect beyond the ledger."""
    key = dedupe_key or _make_key(action, target, detail)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "target": target,
           "detail": detail[:1000], "outcome": outcome, "dedupe_key": key}
    p = _append("actions", rec)
    return json.dumps({"success": True, "logged": rec, "ledger": str(p)}, ensure_ascii=False)


def forge_queue_action(action: str, target: str = "", detail: str = "",
                       due: str = "", dedupe_key: str = "", task_id: Optional[str] = None) -> str:
    """Enqueue a business action for the loop to process.

    Idempotent on dedupe_key: enqueueing the same action twice returns the existing entry
    rather than duplicating it. This is what makes a re-firing cron loop safe.
    """
    key = dedupe_key or _make_key(action, target, detail)
    existing = {r.get("dedupe_key") for r in _read_jsonl("queue", limit=2000)}
    if key in existing:
        return json.dumps({"success": True, "queued": False, "reason": "already queued",
                           "dedupe_key": key}, ensure_ascii=False)
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "target": target,
           "detail": detail[:1000], "due": due, "status": "pending", "dedupe_key": key}
    p = _append("queue", rec)
    return json.dumps({"success": True, "queued": True, "entry": rec, "ledger": str(p)},
                      ensure_ascii=False)


def forge_list_queue(status: str = "pending", limit: int = 50, task_id: Optional[str] = None) -> str:
    """Read the action queue."""
    rows = _read_jsonl("queue", limit=2000)
    if status and status != "all":
        rows = [r for r in rows if r.get("status") == status]
    return json.dumps({"count": len(rows), "entries": rows[-limit:]}, ensure_ascii=False)


def forge_record_metric(name: str, value: float, note: str = "", task_id: Optional[str] = None) -> str:
    """Append a metric datapoint. This is how the loop learns whether a move worked."""
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "metric": name,
           "value": value, "note": note[:500]}
    p = _append("metrics", rec)
    return json.dumps({"success": True, "recorded": rec, "ledger": str(p)}, ensure_ascii=False)


def forge_send_message(channel: str, to: str, body: str, subject: str = "",
                       estimated_cost_usd: float = 0.01, dedupe_key: str = "",
                       task_id: Optional[str] = None) -> str:
    """Send a message on a channel. SIDE EFFECT — kernel-gated and dry-run by default.

    In dry-run (FORGE_EXEC_LIVE unset) nothing is sent: the call is gated, recorded, and the
    return says what WOULD have happened. Set FORGE_EXEC_LIVE=1 to actually send.
    """
    action = "send_message"
    key = dedupe_key or _make_key(action, f"{channel}:{to}", body)

    if key in _seen_keys("actions"):
        return json.dumps({"success": True, "sent": False, "reason": "already sent (idempotent)",
                           "dedupe_key": key}, ensure_ascii=False)

    gate = _kernel_gate(action, estimated_cost_usd, trace_id=key)
    if not gate["allowed"]:
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "target": f"{channel}:{to}",
               "detail": body[:500], "outcome": "blocked", "reason": gate["reason"],
               "dedupe_key": key}
        _append("actions", rec)
        return json.dumps({"success": False, "sent": False, "blocked": True,
                           "verdict": gate["verdict"], "reason": gate["reason"]},
                          ensure_ascii=False)

    live = _env_flag("FORGE_EXEC_LIVE")
    outcome = "sent" if live else "dry_run"
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, "target": f"{channel}:{to}",
           "subject": subject, "detail": body[:500], "outcome": outcome,
           "gate_verdict": gate["verdict"], "dedupe_key": key}
    p = _append("actions", rec)

    if not live:
        return json.dumps({
            "success": True, "sent": False, "dry_run": True, "dedupe_key": key,
            "would_have": f"send {channel} message to {to}",
            "gate_verdict": gate["verdict"],
            "note": "FORGE_EXEC_LIVE is not set — nothing was sent. Set it to execute for real.",
            "ledger": str(p),
        }, ensure_ascii=False)

    # Live send: route through whatever transport the host exposes. Absent a configured
    # transport we do NOT fake success — we report that the action is unconfigured.
    return json.dumps({
        "success": True, "sent": False, "dry_run": False, "dedupe_key": key,
        "gate_verdict": gate["verdict"],
        "note": ("FORGE_EXEC_LIVE is set but no transport is configured for "
                 f"{channel!r}. Wire a sender (the ari-governance/Hermes messaging plugin, or a "
                 "webhook) and call it here. The action is recorded in the ledger."),
        "ledger": str(p),
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_TOOLS = [
    ("forge_log_action", "forge_exec", "Record a business action taken (ledger only, no side effect)",
     {"type": "object", "properties": {
         "action": {"type": "string", "description": "what was done, e.g. 'follow_up_lead'"},
         "target": {"type": "string", "description": "who/what it was done to"},
         "detail": {"type": "string", "description": "free-text detail"},
         "outcome": {"type": "string", "description": "done|skipped|failed"},
         "dedupe_key": {"type": "string", "description": "idempotency key; omit to auto-derive"},
     }, "required": ["action"]},
     forge_log_action),

    ("forge_queue_action", "forge_exec", "Enqueue a business action for the loop to process (idempotent)",
     {"type": "object", "properties": {
         "action": {"type": "string"},
         "target": {"type": "string"},
         "detail": {"type": "string"},
         "due": {"type": "string", "description": "ISO date or free text"},
         "dedupe_key": {"type": "string"},
     }, "required": ["action"]},
     forge_queue_action),

    ("forge_list_queue", "forge_exec", "Read the pending business action queue",
     {"type": "object", "properties": {
         "status": {"type": "string", "description": "pending|all"},
         "limit": {"type": "integer"},
     }, "required": []},
     forge_list_queue),

    ("forge_record_metric", "forge_exec", "Append a metric datapoint so the loop can measure outcomes",
     {"type": "object", "properties": {
         "name": {"type": "string", "description": "e.g. 'revenue', 'leads', 'aov'"},
         "value": {"type": "number"},
         "note": {"type": "string"},
     }, "required": ["name", "value"]},
     forge_record_metric),

    ("forge_send_message", "forge_exec",
     "Send a message on a channel. Kernel-gated, idempotent, DRY-RUN unless FORGE_EXEC_LIVE=1",
     {"type": "object", "properties": {
         "channel": {"type": "string", "description": "email|whatsapp|slack|sms"},
         "to": {"type": "string"},
         "body": {"type": "string"},
         "subject": {"type": "string"},
         "estimated_cost_usd": {"type": "number"},
         "dedupe_key": {"type": "string"},
     }, "required": ["channel", "to", "body"]},
     forge_send_message),
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
    mode = "LIVE" if _env_flag("FORGE_EXEC_LIVE") else "DRY-RUN"
    logger.info("forge-exec: %d tools registered (%s), ledger at %s",
                len(_TOOLS), mode, ledger_dir())
