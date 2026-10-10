# V117 · ACCELERATE — Nicole Forsgren, Jez Humble, Gene Kim
Tier 3 · Product · Tree Memory

## ROOT — the deepest truth
Software delivery performance drives business performance. The research (4 years, 23,000+ data points from 2,000+ organizations) proves that companies with elite DevOps practices deploy 208x more frequently, have 106x faster lead time from commit to deploy, recover from incidents 2,604x faster, and have 7x lower change failure rates. These aren't just tech metrics — elite performers are 2x more likely to exceed profitability, market share, and productivity goals.

## TRUNK — core thesis
Four key metrics define software delivery performance: (1) Deployment Frequency — how often you deploy to production, (2) Lead Time for Changes — time from code committed to code running in production, (3) Mean Time to Restore (MTTR) — time from incident detection to resolution, (4) Change Failure Rate — percentage of deploys that cause incidents. These form a single construct: speed and stability are NOT trade-offs — high performers excel at both. The enablers are: continuous delivery, trunk-based development, loosely coupled architecture, automated testing, comprehensive monitoring, and a generative culture (high trust, information flow, learning).

## BRANCHES & LEAVES

### Branch 1 — The 4 key metrics (DORA)
├─ Deployment frequency: elite = on-demand (multiple per day), high = 1/day to 1/week, medium = 1/week to 1/month, low = <1/month
├─ Lead time for changes: elite = <1 hour, high = 1 day to 1 week, medium = 1 week to 1 month, low = 1-6 months
├─ MTTR: elite = <1 hour, high = <1 day, medium = <1 week, low = >1 week
├─ Change failure rate: elite = 0-15%, high = 16-30%, medium = 21-30% (yes, counterintuitively overlaps), low = 31-45%
└─ LEAF: you can't improve what you don't measure — if you don't know these 4 numbers, start tracking them TODAY

### Branch 2 — Continuous Delivery
├─ 5 principles: (1) build quality in, (2) work in small batches, (3) computers perform repetitive tasks, people solve problems, (4) relentlessly pursue continuous improvement, (5) everyone is responsible
├─ Trunk-based development: merge to main at least daily; branches longer than 1 day = integration risk compounding
├─ Automated testing: unit → integration → acceptance — at least the first two must be automated for continuous delivery
├─ Deployment automation: one-click deploys, self-service for developers, no manual approval gates for routine changes
└─ LEAF: if it hurts, do it more often — the pain of infrequent deploys is the cost of the practices that make them infrequent

### Branch 3 — Architecture
├─ Loosely coupled architecture: teams can test, deploy, and change their services independently
├─ Cloud infrastructure (IaaS/PaaS): strongly correlated with higher delivery performance
├─ Empowered teams: teams choose their own tools and make architecture decisions — no central approval board
├─ Testability built into design: if you can't test it, you can't change it safely
└─ LEAF: when architecture review means "a committee of people who won't maintain it reviews a diagram," velocity dies

### Branch 4 — Culture (Westrum organizational typology)
├─ Generative (performance-oriented): high cooperation, messengers rewarded, risks shared, bridging encouraged
├─ Bureaucratic (rule-oriented): narrow responsibilities, messengers tolerated, risks managed by rules
├─ Pathological (power-oriented): low cooperation, messengers shot, risks hidden, bridging discouraged
├─ Lean management practices (limit WIP, visual displays, monitoring) + generative culture = highest performance
└─ LEAF: if people hide problems because they fear blame, your deployment metrics will look fine — but your incidents won't

## FRUIT — how SmartDecigen applies this
- WHEN a founder says engineering is slow → APPLY the 4 metrics: measure deployment frequency and lead time first — you can't diagnose without data.
- WHEN releases are scary → APPLY the "if it hurts, do it more often" principle: increase deploy frequency until it becomes boring.
- WHEN tech debt is accumulating → APPLY the architecture dimension: is the architecture loosely coupled? Can teams deploy independently?
- WHEN incidents occur → APPLY blameless post-mortem culture: what process allowed this, not who caused this?
- WHEN hiring engineers → APPLY the culture dimension: are you building a generative or pathological engineering culture?

## SEEDS — injectable one-liners
- "If it hurts, do it more often. Deploy 3x a day until it's boring."
- "Speed and stability are not a trade-off. The best teams have both."
- "Branches longer than a day are compounding integration risk."
- "If your deploy takes a weekend, you're doing it wrong."
- "The metric to watch: how long from commit to customer?"

## GRAFTS — connections
- → The Lean Startup (Ries): the Build-Measure-Learn cycle that Accelerate makes fast and safe.
- → High Output Management (Grove): the management practices that enable high-performing engineering teams.
- → The Goal (Goldratt): theory of constraints applied to software delivery — what's your bottleneck?
