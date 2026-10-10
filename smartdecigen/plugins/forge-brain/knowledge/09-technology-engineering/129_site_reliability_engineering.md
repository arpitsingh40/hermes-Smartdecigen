# V129 · SITE RELIABILITY ENGINEERING — Google (Beyer, Jones, Petoff, Murphy)
Tier 3 · Technology · Tree Memory

## ROOT
SRE is what happens when you ask a software engineer to design an operations function. Instead of manually managing servers, SREs write software to manage systems. The core principles: (1) reliability is a feature, (2) 100% reliability is neither possible nor desirable — users don't notice the difference between 99.9% and 99.99%, (3) an error budget defines how much unreliability is acceptable, (4) automate everything that repeats, (5) blameless post-mortems drive learning. SRE is one of the most important operations frameworks ever written — it has been adopted by thousands of organizations beyond Google.

## TRUNK
Service Level Objectives (SLOs) and Error Budgets: define the target reliability (e.g., 99.9% uptime/month). The error budget = 1 - SLO (0.1% = 43 minutes of allowed downtime per month). If you're within budget, ship features. If you've exhausted the budget, freeze features and invest in reliability. This creates a healthy tension between devs (want to ship) and ops (want stability). Monitoring: alert on symptoms (user-facing problems), not causes (server metrics). Eliminate toil — manual, repetitive, automatable work. Post-mortems: blameless, focus on process fixes, every incident produces action items.

## BRANCHES
- Error budgets: the single most powerful concept. Without an error budget, every outage is a political fight between product and engineering. With it, the math decides.
- Toil elimination: if a human does it, it's toil. If a machine does it, it's automation. Target: <50% of SRE time on toil.
- Monitoring: 4 golden signals — latency (how long), traffic (how much), errors (failure rate), saturation (how full). Alert on symptoms, not causes.
- Incident management: defined roles (incident commander, communications lead, operations lead). Blameless post-mortem within 48 hours. No "human error" as root cause — every human error had a process that allowed it.
- On-call: rotational, two-person coverage, escalation path clear. Burnout from on-call is the #1 SRE retention killer.

## FRUIT
- WHEN reliability is poor → APPLY error budget: what's your SLO, what's the budget, have you exceeded it? If not, this is expected.
- WHEN incidents recur → APPLY post-mortem discipline: was the post-mortem blameless? Were action items completed? Did the process change?
- WHEN on-call is burning people out → APPLY toil elimination: what percentage of on-call work is repetitive, scriptable, or automatable?
- WHEN releases are risky → APPLY error budget gate: if budget is exhausted, freeze features. If budget is healthy, ship faster to get feedback faster.

## SEEDS
- "100% reliability is not the goal — users can't tell the difference."
- "The error budget makes the shipping/reliability tension mathematical, not political."
- "Eliminate toil. If a human repeats it, write software to do it."
- "Blameless post-mortems: every incident is a process failure, not a person failure."
- "Alert on symptoms (users are affected), not causes (server is at 80%)."

## GRAFTS
- → Accelerate: the DORA metrics that SRE practices directly improve.
- → The Goal: theory of constraints — MTTR is a constraint on throughput.
- → High Output Management: the management practices for SRE teams.
