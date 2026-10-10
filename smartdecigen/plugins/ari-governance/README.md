# ari-governance — Hermes plugin

Gates money-moving Hermes tool calls through the **ARI governance kernel** before they execute.

The kernel (Rust + Postgres, in `unified-platform/kernel/`) owns spend caps, kill switches,
tenant isolation, approvals and the audit trail. Hermes owns the tool loop. This plugin is the
seam between them.

```
Hermes agent
   │  wants to call send_email
   ▼
pre_tool_call hook ──POST /api/v1/gate──▶ ARI kernel
   │                                        ├─ tenant check (403 if org mismatch)
   │                                        ├─ kill switch (global + per-org)
   │                                        ├─ weekly spend cap (Postgres, Monday-keyed)
   │                                        └─ audit row written
   │  ◀── {gate: "allowed" | "dry_run" | "blocked", reason, used, cap}
   ▼
tool runs (or is blocked with a message the model can relay)
   │
   ▼
post_tool_call hook ──POST /api/v1/spend──▶ kernel commits actual cost
```

## Why it fails closed

Hermes documents `pre_tool_call` as failing **closed** on timeout (30s cap). This plugin makes
that explicit for the money path: if the kernel is unreachable, the gated tool is **blocked**,
not allowed. An unreachable money gate must not silently permit spend.

Override for local development only: `ARI_GATE_FAIL_OPEN=1`.

## What gets gated

Only money-moving tools. Gating everything would put a network round-trip on every turn and
make the agent useless when the kernel is down.

| Tool | Action sent | Est. cost |
|---|---|---|
| `send_email`, `email_send` | `email.send` | $0.01 |
| `send_message` | `message.send` | $0.01 |
| `image_generate` | `image.generate` | $0.04 |
| `video_generate` | `video.generate` | $0.50 |
| `text_to_speech` | `tts.generate` | $0.02 |
| `browser_exec` | `browser.session` | $0.02 |
| `computer_use` | `computer.session` | $0.05 |
| `deploy` | `deploy.run` | $0.10 |

Add org-specific tools with `ARI_GATE_EXTRA_TOOLS=crm_write,ads_spend` (flat $0.01 each).

`read_file`, `terminal`, `search_files`, `write_file` and every other local tool pass straight
through — they never touch the kernel.

## Install

```bash
# 1. Start the kernel (needs Postgres; migrations run on boot)
cd unified-platform/kernel/runtime/src/host
export ARI_JWT_SECRET='a-real-secret-at-least-32-chars-long'
export ARI_POSTGRES_URL='postgres://user:pass@localhost/ari'
cargo run --release            # serves on :8080

# 2. Mint a token for the org (HS256, same secret)
#    Claims: sub, org_id, role, exp, iat, iss="ari"

# 3. Configure the plugin
export ARI_KERNEL_URL='http://127.0.0.1:8080'
export ARI_JWT='<token>'
export ARI_ORG_ID='org_<your-org>'

# 4. Place the plugin where Hermes loads user plugins from, then restart
#    %LOCALAPPDATA%\hermes\plugins\ari-governance\   (Windows)
#    ~/.hermes/plugins/ari-governance/               (Linux/macOS)

# 5. Verify Hermes sees the hooks
hermes plugins list
```

Set a cap for the org (else the global default applies):

```sql
INSERT INTO org_governance (org_id, config) VALUES ('org_acme', '{
  "org_id": "org_acme",
  "kill_switch": false,
  "dry_run": false,
  "weekly_spend_cap_usd": 50.0,
  "allowed_capabilities": [], "blocked_capabilities": [],
  "require_approval_for": ["email.send"],
  "max_tool_calls_per_invocation": null
}'::jsonb)
ON CONFLICT (org_id) DO UPDATE SET config = EXCLUDED.config;
```

## Verify

```bash
# Unit tests — gate policy, verdict mapping, failure modes (no kernel, no Postgres)
python -m pytest test_gate_plugin.py -v

# Integration — real HTTP round-trip against a mock kernel
python integration_check.py
```

`integration_check.py` exercises: blocked-when-over-cap → allowed-after-cap-raise → spend
committed-on-success → no-spend-on-error → ungated-tool-never-calls-kernel → fail-closed-when-
kernel-down. It prints `ALL CHECKS PASSED` on success.

## Audit trail

Every gate decision writes a row, allowed and blocked alike:

```sql
SELECT ts, actor, action, resource, trace_id, details
FROM audit_log WHERE org_id = 'org_acme' ORDER BY ts DESC LIMIT 20;
```

`action` is `gate.allowed`, `gate.dry_run`, `gate.blocked` or `spend.record`. `trace_id` is the
Hermes session id, so a spend can be traced back to the conversation that caused it.

## Env reference

| Var | Default | Meaning |
|---|---|---|
| `ARI_KERNEL_URL` | `http://127.0.0.1:8080` | Kernel base URL |
| `ARI_JWT` | — | Bearer token (required to gate) |
| `ARI_ORG_ID` | — | Org to gate against (required) |
| `ARI_GATE_TIMEOUT` | `5` | Seconds to wait on the kernel (hook cap is 30) |
| `ARI_GATE_EXTRA_TOOLS` | — | Comma-separated extra tool names to gate |
| `ARI_GATE_DISABLE` | — | `1` = pass everything through (dev) |
| `ARI_GATE_FAIL_OPEN` | — | `1` = allow on kernel failure. **Never in production.** |
