# forge-brain — reasoning lenses on every turn

Ports SmartDecigen's decision-science layer onto Hermes as a `pre_llm_call` hook.

Two things get injected before the model reasons:

1. **Decision category** — a keyword router into 9 founder decision types, each carrying a
   step-by-step reasoning algorithm (e.g. `DEAL/NEGOTIATION ALGORITHM: 1) Trace the
   counterparty's incentives…`).
2. **Reasoning lenses** — the 3 most relevant modules from a **166-book** decision-science
   library, scored against the turn, injected as *applied frameworks* with their FRUIT rules
   ("WHEN a founder states a confident forecast → APPLY outside-view demand…").

Zero LLM cost. An off-topic turn injects nothing.

## Why a hook, not a system prompt

Hermes' prompt-caching invariant forbids rebuilding the system prompt mid-conversation. This
content changes every turn, so it must ride `pre_llm_call` — which Hermes documents as injecting
into the **user message**, leaving the cached prefix intact. Putting it in a system-prompt
section would break caching and multiply cost.

## Install

```bash
# files already in place at:
#   %LOCALAPPDATA%\hermes\plugins\forge-brain\     (Windows)
#   ~/.hermes/plugins/forge-brain/                 (Linux/macOS)

hermes plugins enable forge-brain
```

Verify:
```bash
python -m pytest test_forge_brain.py -v     # 35 unit tests
python integration_check.py                 # prints the real injected block
```

## Behaviour

| Message | Result |
|---|---|
| `should I sign the distributor deal at these terms` | injects `deal negotiation` + lenses |
| `we already invested 5 lakh in this and I know it will work` | injects `money allocation` + Kahneman/Munger/Taleb |
| `should we hire a second salesperson or a cofounder` | injects `people team` + lenses |
| `we are in crisis and need to survive, emergency runway` | injects `crisis survival` + lenses |
| `read the file at /tmp/x` | **nothing** |
| `git status` | **nothing** |
| `convert this to json` | **nothing** |

## The one deliberate deviation from the source

The original matched every trigger as a plain substring and injected lenses whenever any module
scored. That is fine in a business-coaching conversation where every message is about the
business. In a general-purpose agent it produces confident nonsense, because the lens vocabulary
is business-domain:

| Trigger | Matched inside | Fired |
|---|---|---|
| `lease` | "**plea**se" | `taleb_antifragile` on "yes please" |
| `director` | "**director**y" | `feld_boards` on "list the files in this directory" |
| `cto` | "dire**cto**ry" | `people_team` on a file task |
| `convert` | "**convert** this to json" | `bush_plg` + `cialdini_influence` on a file task |
| `code` | "explain this **code**" | `feathers_legacy` on a question about source |

Two fixes, both in `__init__.py`:

1. **Whole-word matching with a suffix list** for single-word triggers (`s|es|ed|ing|ly|ity|ion|ive|ment|al|er|est`).
   Keeps intentional prefixes working (`exclusiv` → "exclusivity") and stemming (`confident` →
   "confidence"), stops `director` → "directory". Multi-word phrases keep substring matching.
2. **Category gating** — lenses are injected only when the message also routes to a decision
   category. The category keywords are specific business terms, so they gate the generic lens
   vocabulary to turns that are actually about a business decision.

`test_parity_with_smartdecigen_on_business_messages` asserts the port still selects **identical**
lenses to the original on real business turns — the deviation is only in *how* triggers match.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | matchers, router, scorer, block builder, hook |
| `lenses.json` | 166 modules: id, book, triggers, lens instruction |
| `categories.json` | 9 categories: keywords, preferred lenses, algorithm |
| `knowledge/` | 166 markdown files (1.2 MB) — FRUIT rules per book |
| `test_forge_brain.py` | 35 unit tests incl. source-parity |
| `integration_check.py` | prints real injected blocks per message |

## Env

| Var | Default | Meaning |
|---|---|---|
| `FORGE_BRAIN_DISABLE` | — | `1` = inject nothing |
| `FORGE_BRAIN_MAX_LENSES` | `3` | lenses per turn |
| `FORGE_BRAIN_MIN_SCORE` | `2` | minimum trigger score to select a lens |
| `FORGE_BRAIN_MAX_CHARS` | `2400` | hard cap on the injected block |
| `FORGE_BRAIN_FRUIT` | `1` | `0` = lens text only, skip knowledge FRUIT rules |

## Updating

This plugin lives outside the Hermes git checkout, so `hermes update` never touches it. If a
Hermes update changes the `pre_llm_call` contract, re-run `integration_check.py` — it exercises
the hook exactly as Hermes calls it.
