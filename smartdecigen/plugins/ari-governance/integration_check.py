"""End-to-end check: the plugin, over real HTTP, against a mock kernel.

This is the integration proof that the seam works — not a unit test of the logic (that is
test_gate_plugin.py), but an actual httpx round-trip where the plugin asks a live server for a
verdict and blocks a tool call on the answer.

Run:  python integration_check.py
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# --- the mock kernel ------------------------------------------------------------------
# Mimics kernel/runtime/src/host/src/gate.rs: POST /api/v1/gate is a pure read that returns
# {gate, reason, weekly_spend_used_usd, weekly_spend_cap_usd}. POST /api/v1/spend commits.

STATE = {"used": 10.00, "cap": 10.00}
CALLS = []


class MockKernel(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            return self._json(401, {"error": "missing Authorization"})
        CALLS.append((self.path, body))

        if self.path == "/api/v1/gate":
            cost = float(body.get("estimated_cost_usd", 0.0))
            if STATE["used"] + cost > STATE["cap"]:
                return self._json(200, {
                    "gate": "blocked",
                    "reason": f"Weekly spend cap exceeded: ${STATE['used']:.2f} / ${STATE['cap']:.2f}",
                    "org_id": body["org_id"], "action": body.get("action", ""),
                    "estimated_cost_usd": cost,
                    "weekly_spend_used_usd": STATE["used"],
                    "weekly_spend_cap_usd": STATE["cap"],
                    "trace_id": "trace-mock",
                })
            return self._json(200, {
                "gate": "allowed", "reason": None,
                "org_id": body["org_id"], "action": body.get("action", ""),
                "estimated_cost_usd": cost,
                "weekly_spend_used_usd": STATE["used"],
                "weekly_spend_cap_usd": STATE["cap"],
                "trace_id": "trace-mock",
            })

        if self.path == "/api/v1/spend":
            STATE["used"] += float(body.get("amount_usd", 0.0))
            return self._json(200, {"ok": True, "weekly_spend_used_usd": STATE["used"]})

        return self._json(404, {"error": "not found"})


def main():
    server = HTTPServer(("127.0.0.1", 0), MockKernel)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    os.environ["ARI_KERNEL_URL"] = f"http://127.0.0.1:{port}"
    os.environ["ARI_JWT"] = "test-token"
    os.environ["ARI_ORG_ID"] = "org_test"

    import __init__ as gate  # noqa

    ok = True

    # 1. A gated tool when the budget is nearly spent -> BLOCKED.
    out = gate.on_pre_tool_call(tool_name="send_email", args={"to": "a@b.c"}, session_id="s1")
    blocked = out is not None and out["action"] == "block"
    print(f"[1] send_email @ $10.00/$10.00 -> {'BLOCKED' if blocked else 'ALLOWED (WRONG)'}")
    print(f"    message: {out['message'][:110] if out else '-'}")
    ok &= blocked

    # 2. Raise the cap; the same call is now allowed.
    STATE["cap"] = 50.00
    out = gate.on_pre_tool_call(tool_name="send_email", args={"to": "a@b.c"}, session_id="s2")
    allowed = out is None
    print(f"[2] send_email @ $10.00/$50.00 -> {'ALLOWED' if allowed else 'BLOCKED (WRONG)'}")
    ok &= allowed

    # 3. Successful tool -> spend committed to the kernel.
    before = STATE["used"]
    gate.on_post_tool_call(tool_name="send_email", result=json.dumps({"success": True}), session_id="s2")
    committed = abs(STATE["used"] - (before + 0.01)) < 1e-9
    print(f"[3] spend commit -> used {before:.2f} -> {STATE['used']:.2f} ({'OK' if committed else 'WRONG'})")
    ok &= committed

    # 4. Failed tool -> no spend.
    before = STATE["used"]
    gate.on_post_tool_call(tool_name="send_email", result=json.dumps({"error": "smtp down"}), session_id="s3")
    print(f"[4] failed tool -> used unchanged ({'OK' if STATE['used'] == before else 'WRONG'})")
    ok &= STATE["used"] == before

    # 5. Ungated tool never touches the kernel.
    n = len(CALLS)
    gate.on_pre_tool_call(tool_name="read_file", args={"path": "/x"})
    print(f"[5] read_file -> no kernel call ({'OK' if len(CALLS) == n else 'WRONG'})")
    ok &= len(CALLS) == n

    # 6. Kernel down -> fail closed.
    server.shutdown()
    out = gate.on_pre_tool_call(tool_name="send_email", args={}, session_id="s4")
    closed = out is not None and out["action"] == "block"
    print(f"[6] kernel down -> {'BLOCKED (fail-closed)' if closed else 'ALLOWED (WRONG)'}")
    ok &= closed

    print(f"\nkernel calls observed: {len(CALLS)} -> {[c[0] for c in CALLS]}")
    print("RESULT:", "ALL CHECKS PASSED" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
