"""End-to-end check: one full loop iteration against real state on disk.

Exercises the actual loop the way a cron job would:
  state -> decide -> act (gated, idempotent) -> measure -> report -> re-read

Run:  python integration_check.py
"""

import json
import os
import shutil
import sys
import tempfile
import importlib.util
from pathlib import Path

_PLUGINS = Path(__file__).resolve().parent.parent


def _load(mod_name: str, plugin_dir: str):
    """Load a plugin's __init__.py by path — both are named __init__, so a plain import collides."""
    path = _PLUGINS / plugin_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


fx = _load("forge_exec_mod", "forge-exec")   # execution tools
fl = _load("forge_loop_mod", "forge-loop")   # loop state helpers


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="forge-loop-e2e-")
    os.environ["FORGE_LOOP_DIR"] = tmp
    os.environ["FORGE_EXEC_DIR"] = tmp
    # dry-run: no kernel credentials, fail-open so the gate lets the action through
    os.environ["FORGE_EXEC_FAIL_OPEN"] = "1"
    os.environ.pop("FORGE_EXEC_LIVE", None)

    ok = True
    try:
        print(f"state dir: {tmp}\n")

        # --- iteration 1: cold start, nothing to decide from -------------------------------
        s = json.loads(fl.forge_loop_state())
        print(f"[1] cold start      queue={s['queue']['pending']} metrics={len(s['metrics'])} runs={len(s['last_runs'])}")
        ok &= s["queue"]["pending"] == 0

        # --- the agent decides: queue two follow-ups and send one ---------------------------
        q1 = json.loads(fx.forge_queue_action(action="follow_up_lead", target="lead-17",
                                              detail="quoted 3 weeks ago", dedupe_key="fu-17-w42"))
        q2 = json.loads(fx.forge_queue_action(action="follow_up_lead", target="lead-22",
                                              detail="asked for pricing", dedupe_key="fu-22-w42"))
        print(f"[2] queued 2 actions: {q1['queued']} {q2['queued']}")

        # idempotency: the same cron firing again must NOT duplicate
        q1b = json.loads(fx.forge_queue_action(action="follow_up_lead", target="lead-17",
                                               detail="quoted 3 weeks ago", dedupe_key="fu-17-w42"))
        print(f"[3] re-fire same key -> queued={q1b['queued']} ({q1b['reason']})")
        ok &= q1b["queued"] is False

        # --- act: send a follow-up (gated, idempotent, dry-run) -----------------------------
        sent = json.loads(fx.forge_send_message(channel="whatsapp", to="+919000000017",
                                                body="Hi — following up on the quote from 3 weeks ago.",
                                                dedupe_key="fu-17-w42-send"))
        print(f"[4] send            dry_run={sent.get('dry_run')} sent={sent.get('sent')} verdict={sent.get('gate_verdict')}")
        ok &= sent.get("dry_run") is True and sent.get("sent") is False

        sent2 = json.loads(fx.forge_send_message(channel="whatsapp", to="+919000000017",
                                                 body="Hi — following up on the quote from 3 weeks ago.",
                                                 dedupe_key="fu-17-w42-send"))
        print(f"[5] re-send         sent={sent2.get('sent')} ({sent2.get('reason')})")
        ok &= "already sent" in (sent2.get("reason") or "")

        # --- measure: record the leading indicator -----------------------------------------
        fx.forge_record_metric(name="followups_sent", value=1, note="week 42")
        print("[6] recorded metric followups_sent=1")

        # --- report ------------------------------------------------------------------------
        fl.forge_loop_record_run(decision="Chase the two stale leads from 3 weeks ago; "
                                          "followups_sent is the leading indicator, reply rate lags.",
                                 actions_taken=2, note="1 send (dry-run), 2 queued",
                                 next_check="reply rate on lead-17 / lead-22")

        # --- iteration 2: the state must now carry the history ------------------------------
        s2 = json.loads(fl.forge_loop_state())
        print(f"\n[7] iteration 2     queue={s2['queue']['pending']} "
              f"actions={len(s2['recent_actions'])} metrics={list(s2['metrics'])} runs={len(s2['last_runs'])}")
        ok &= s2["queue"]["pending"] == 2
        ok &= len(s2["recent_actions"]) == 1
        ok &= s2["metrics"]["followups_sent"]["latest"] == 1
        ok &= len(s2["last_runs"]) == 1

        # --- iteration 2 delta: record a new value, the loop can now see a trend -------------
        fx.forge_record_metric(name="followups_sent", value=3, note="week 43")
        s3 = json.loads(fl.forge_loop_state())
        m = s3["metrics"]["followups_sent"]
        print(f"[8] trend           latest={m['latest']} previous={m['previous']} delta={m['delta']}")
        ok &= m["delta"] == 2

        # --- complete one queued action -----------------------------------------------------
        done = json.loads(fl.forge_loop_complete_action(dedupe_key="fu-17-w42", outcome="done"))
        s4 = json.loads(fl.forge_loop_state())
        print(f"[9] completed fu-17-w42 -> pending now {s4['queue']['pending']}")
        ok &= done["success"] is True
        ok &= s4["queue"]["pending"] == 1

        # --- the ledger on disk --------------------------------------------------------------
        files = sorted(os.listdir(tmp))
        print(f"\n[10] ledger files: {files}")
        ok &= set(files) == {"queue.jsonl", "actions.jsonl", "metrics.jsonl", "runs.jsonl"}

        print("\n" + "=" * 70)
        print("ledger contents")
        print("=" * 70)
        for f in files:
            with open(os.path.join(tmp, f), encoding="utf-8") as fh:
                n = len(fh.read().strip().splitlines())
            print(f"  {f:<16} {n} line(s)")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nRESULT: {'ALL CHECKS PASSED' if ok else 'FAILURES PRESENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
