# V148 · CONTINUOUS DELIVERY — Jez Humble & David Farley
Tier 3 · Technology · Tree Memory

## ROOT
Continuous delivery is the ability to get changes — features, configuration changes, bug fixes, experiments — into production safely, quickly, and sustainably. The key test: is your software always in a deployable state? If not, you're accumulating risk. CD transforms the release process from a multi-week stressful event to a boring push-button operation.

## TRUNK
Principles: (1) Build quality in — never inspect quality at the end. (2) Work in small batches — smaller changes = easier to find the bug. (3) Relentless automation — every repetitive task is a candidate for automation. (4) Continuous improvement — the deployment pipeline is never finished. (5) Everyone is responsible — developers own deployment, ops owns the platform. The deployment pipeline: commit → build → unit test → integration test → acceptance test → performance test → deploy to staging → deploy to production. Every stage is automated. Manual gates exist only for compliance (not convenience). Rollback is a one-click operation. The deployment pipeline is the single source of truth for build, test, and deploy status.

## FRUIT
- WHEN releases are painful → APPLY the deployment pipeline: how automated is your path from commit to production?
- WHEN bugs reach production → APPLY the quality principle: were the tests that should have caught this automated?

## SEEDS
- "Your software should always be in a deployable state. If it isn't, you're accumulating risk."
- "Smaller changes = easier bugs to find."
- "The deployment pipeline is the single source of truth. If it's broken, the team stops to fix it."

## GRAFTS
- → Accelerate: the 4 metrics (deploy frequency, lead time, MTTR, change failure rate) that CD enables.
- → Site Reliability Engineering: the operational layer on top of CD.
