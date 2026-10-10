# V118 · THE GOAL — Eliyahu Goldratt
Tier 3 · Operations · Tree Memory

## ROOT — the deepest truth
The goal of any business is to make money, and every action that does not move the organization toward that goal is waste. The Theory of Constraints (TOC) states that every system has exactly ONE constraint that determines its throughput. Optimizing anything other than the constraint is wasted effort — you can only go as fast as your slowest step. Identify the constraint, exploit it, subordinate everything else to it, elevate it, then repeat.

## TRUNK — core thesis
Told as a business novel (plant manager Alex Rogo saves his factory in 3 months or it closes), Goldratt introduces the 5 Focusing Steps: (1) IDENTIFY the constraint — the single resource, policy, or process that limits throughput. (2) EXPLOIT the constraint — get maximum output from the constraint without additional investment (reduce downtime, never let it be idle, feed it only quality inputs). (3) SUBORDINATE everything to the constraint — all other resources run at the constraint's pace; faster is waste. (4) ELEVATE the constraint — if still the bottleneck after exploitation, invest to increase its capacity. (5) REPEAT — once the constraint is broken, a new constraint emerges elsewhere. The key metrics are: Throughput (rate of generating money through sales), Inventory (money invested in things to sell), and Operating Expense (money spent turning inventory into throughput).

## BRANCHES & LEAVES

### Branch 1 — The 5 Focusing Steps
├─ Step 1: Identify — look for the biggest queue, the resource everyone waits on, the step at 100% utilization while others are at 60%
├─ Step 2: Exploit — wring every drop from the constraint: eliminate downtime, run through breaks, ensure no bad inputs reach it, prioritize constraint work above all else
├─ Step 3: Subordinate — non-constraints should NOT operate at 100%; they should produce at exactly the constraint's rate. Overproduction before the constraint is inventory (waste)
├─ Step 4: Elevate — invest to increase constraint capacity: more people, better equipment, outsourcing
├─ Step 5: Go back to Step 1 — inertia is the biggest enemy; the old constraint may no longer be the constraint
└─ LEAF: if you have 10 improvement projects running simultaneously, 9 of them are on non-constraints — kill them and focus on the one that matters

### Branch 2 — Throughput Accounting
├─ Throughput (T) = Sales revenue - Truly Variable Costs (raw materials, commissions). Labor is NOT truly variable in most businesses.
├─ Inventory (I) = money the system has invested in things it intends to sell. Finished goods, WIP, raw materials — all cash tied up.
├─ Operating Expense (OE) = money the system spends turning Inventory into Throughput. Salaries, rent, utilities, depreciation.
├─ The goal: increase T while reducing I and OE. Cost-cutting alone (reducing OE) has a ceiling; improving T has no theoretical ceiling.
└─ LEAF: a cost reduction that reduces T (firing a key person, cutting quality) is worse than no action — measure all decisions against T, I, OE

### Branch 3 — Dependent events and statistical fluctuations
├─ Dice game demonstration: when processes are sequential and variable, the combined output is determined by the worst step, not the average
├─ Buffers protect the constraint from upstream variability: time buffers (schedule work early before the constraint), stock buffers (keep a queue of work ready)
├─ Local optima ≠ global optimum: making every individual step efficient makes the whole system LESS efficient (because inventory piles up)
└─ LEAF: measuring local efficiency (machine utilization, developer commits) creates behavior that destroys throughput

### Branch 4 — Applying TOC beyond manufacturing
├─ Software development: the constraint is often code review, QA, or deployment — not coding speed. Hiring more developers when QA is the constraint increases WIP, not throughput.
├─ Sales: the constraint might be qualified leads (not closers) or pipeline coverage (not demos). Measure the constraint, not the full funnel.
├─ Marketing: the constraint might be content production, a specific channel, or messaging clarity. Doubling ad spend when the constraint is conversion rate burns cash.
└─ LEAF: ask "what is the ONE thing that, if improved, would increase throughput the most?" — that's your constraint; everything else is noise

## FRUIT — how SmartDecigen applies this
- WHEN a founder is overwhelmed with too many projects → APPLY constraint identification: name the ONE bottleneck; kill or pause everything else.
- WHEN growth is slow despite hiring → APPLY the dependent-events check: did you add capacity to the constraint or to non-constraints?
- WHEN a team looks "busy but nothing ships" → APPLY throughput vs local efficiency: are people optimizing for looking busy or for output?
- WHEN prioritizing initiatives → APPLY the T/I/OE lens: which investments increase throughput vs reduce cost? Prioritize throughput.
- WHEN a process change had no effect → APPLY Step 5: did the constraint move? You're optimizing a constraint that no longer exists.

## SEEDS — injectable one-liners
- "A system can only go as fast as its slowest step. What's yours?"
- "Making every step efficient makes the whole system LESS efficient."
- "If you have 10 improvement projects, 9 of them are wasted effort. Find the one constraint."
- "An hour lost at the constraint is an hour lost for the entire system."
- "Hiring more people when the bottleneck isn't people adds cost, not output."

## GRAFTS — connections
- → Thinking in Systems (Meadows): constraints = leverage points; the highest leverage is at the constraint.
- → The 4 Disciplines of Execution: the "one wildly important goal" — same insight, different language.
- → The E-Myth Revisited (Gerber): the founder IS often the constraint in small businesses.
- → Accelerate (Forsgren): applying constraint theory to software delivery — deployment IS the bottleneck.
