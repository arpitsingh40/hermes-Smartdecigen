# FORGE — a business execution OS on Hermes

Seven plugins that turn Hermes into a business operating system: it reasons like a specific
operator, diagnoses where a business is actually broken, plans 10× growth, **executes** actions,
and **runs on a schedule** — with every money-moving action gated through a governance kernel.

All live outside the Hermes git checkout, so `hermes update` never touches them.

| Plugin | Slot | What it does |
|---|---|---|
| **forge-brain** | `pre_llm_call` | Decision category + 3 reasoning lenses from a 166-book library, per turn |
| **forge-growth** | `pre_llm_call` | Business graph, root-cause walker, opportunity scan, 10× growth planner |
| **forge-voice** | `register_system_prompt_section` | The operator persona, cache-safe and frozen per session |
| **forge-confirm** | `pre_llm_call` + `transform_llm_output` | Quality gate on the reply |
| **ari-governance** | `pre_tool_call` / `post_tool_call` | Gates money-moving tools through the ARI kernel; **fails closed** |
| **forge-exec** | 5 tools | The execution layer: idempotent, gated, audited business actions |
| **forge-loop** | 3 tools + skill | The autonomous loop: state → decide → act → measure → report |

**166 unit tests + 4 integration checks.**

## What each layer answers

| Question | Plugin |
|---|---|
| *Should I do this, and how should I think about it?* | forge-brain — 1 of 9 decision types, 3 best of 166 reasoning lenses |
| *Why is my business stuck, and where's the real constraint?* | forge-growth — maps the message to 1 of 16 functions, walks **upstream** through the dependency graph |
| *How do I get 10× from here?* | forge-growth — loops, cadence, milestones, compounding check |
| *How should this sound?* | forge-voice |
| *Is this reply actually good?* | forge-confirm |
| *Is this spend authorised?* | ari-governance |
| *Do it.* | forge-exec — send, queue, log, measure |
| *Do it every day without me.* | forge-loop — cron-driven, state-carrying, self-measuring |

## The execution layer

`forge-exec` is what makes this an OS rather than an advisor. Five tools, every one of them:

- **Idempotent** — a `dedupe_key` makes a repeat a no-op. A cron that fires twice must not email
  the customer twice.
- **Kernel-gated** — money-moving actions ask the kernel first, and **fail closed**.
- **Audited** — every action, including blocked ones, appends a ledger line.
- **Dry-run by default** — side effects require `FORGE_EXEC_LIVE=1`. Explicitly opt in.

| Tool | Effect |
|---|---|
| `forge_send_message` | side effect — gated, idempotent, dry-run unless live |
| `forge_queue_action` | enqueue work (idempotent on key) |
| `forge_log_action` | record a manual step |
| `forge_record_metric` | append a datapoint |
| `forge_list_queue` | read the queue |

## The loop

`forge-loop` carries the state; the **agent is the brain**, deliberately — so the reasoning and
growth layers apply to every iteration. One cron job runs it:

```bash
hermes cron create "every 6h" "Run the forge business loop" --skill forge-business-loop
```

The skill `skills/forge-business-loop` carries the procedure. State lives in
`$HERMES_HOME/forge-exec/` as four append-only ledgers: `queue`, `actions`, `metrics`, `runs`.

Iteration: **state → decide → act → measure → report.** The `runs` ledger is read by the next
iteration, which is how the loop builds history instead of repeating itself. The `metrics` delta
between runs is the only evidence the loop is working.


## The split that matters

Hermes' prompt-caching invariant forbids rebuilding the system prompt mid-conversation. That
forces where each piece goes:

| Content | Varies per turn? | Slot |
|---|---|---|
| Lenses, decision category | yes | `pre_llm_call` → injected into the **user message** |
| Operator persona | no | system prompt section → **frozen** per session |
| Reply quality check | per turn, post-hoc | `transform_llm_output` |
| Spend authorisation | per tool call | `pre_tool_call` |

Getting this wrong is expensive: per-turn content in the system prompt breaks the cached prefix
and multiplies cost. This is why the ports are hooks, not core edits.

## Failure policy — deliberately different per plugin

| Plugin | On error | Why |
|---|---|---|
| `ari-governance` | **fail CLOSED** (block the tool) | Guards money. An unreachable gate must not permit spend. |
| `forge-exec` | **fail CLOSED** (refuse the action) | Same — a money action with no gate is refused. |
| `forge-confirm` | **fail OPEN** (keep the draft) | Guards prose. A good reply already exists; blanking it is worse. |
| `forge-brain`, `forge-growth` | fail open (inject nothing) | Lenses are an enhancement, not a requirement. |
| `forge-voice` | fail open (skip section) | Persona is cosmetic. |
| `forge-loop` | fail open (degrade to empty state) | A read failure must not crash the cron. |

## Enable

```bash
hermes plugins enable forge-brain forge-growth forge-voice forge-exec forge-loop

# OFF by default — costs one extra LLM call per turn
hermes plugins enable forge-confirm
export FORGE_CONFIRM=1

# Requires the kernel running; fails closed
hermes plugins enable ari-governance
export ARI_JWT='<token>' ARI_ORG_ID='org_x' ARI_KERNEL_URL='http://127.0.0.1:8080'

# Side effects stay off until you say otherwise
export FORGE_EXEC_LIVE=1        # only when you mean it

# The loop (once the above is in place)
hermes cron create "every 6h" "Run the forge business loop" --skill forge-business-loop
```

## Verify

```bash
for p in ari-governance forge-brain forge-growth forge-voice forge-confirm forge-exec forge-loop; do
  (cd "$p" && python -m pytest -q)
done
for p in ari-governance forge-brain forge-growth forge-loop; do (cd "$p" && python integration_check.py); done
```

166 unit tests + 4 integration checks. Run these after every `hermes update` — they exercise the
hooks and tools exactly as Hermes calls them, so a contract change shows up here rather than in
production.

## What is NOT ported, and why

| Source | Why not |
|---|---|
| `engine.py::llm_turn` | Hermes owns the turn loop |
| `server.py` + 30 routers | Hermes gateway + dashboard replace them |
| `execution/` MCP dispatcher (4,081 lines) | 50 core tools + MCP + 522 catalog plugins; `forge-exec` carries the business-specific actions |
| `agents.py` (12 agents) | Bot Mode replaces it |
| `doc_memory.py` (RAPTOR) | Hermes memory providers replace it |
| The WASM runtime path | Hermes **is** the runtime |
| The JSON output contract in the SYSTEM prompt | Hermes owns its own response format |
| Health-score persistence (MongoDB) | Optional enrichment via `FORGE_GROWTH_HEALTH` |

## Unproven

The kernel's SQL round-trip against a live Postgres. Everything up to the HTTP boundary is tested;
`check_execution` / `spend_snapshot` against a real database is not. Until that runs,
`ari-governance` and `forge-exec` gate on a service that has never touched a DB.

`forge_send_message` in live mode has **no transport wired** — it records the action and says so
rather than faking a send. That is deliberate: an execution layer that reports success without
sending is worse than one that admits it is unconfigured.
