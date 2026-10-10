# V138 · TRUSTWORTHY ONLINE CONTROLLED EXPERIMENTS — Ron Kohavi, Diane Tang, Ya Xu
Tier 3 · Data · Tree Memory

## ROOT
A/B testing is the dominant method for data-driven decision making in tech companies, but most organizations run A/B tests wrong: they peek at results, stop early, misinterpret p-values, or run underpowered tests. Kohavi (former head of experimentation at Amazon, Microsoft, Airbnb) provides the definitive guide to running trustworthy experiments at scale. The core insight: most ideas that "should work" don't. At Microsoft, only 1/3 of experiments moved the metric in the intended direction. Without rigorous experimentation, you're building on the wrong 2/3.

## TRUNK
Key concepts: (1) Overall Evaluation Criterion (OEC) — the single metric that determines whether a change is good. (2) Statistical power: minimum sample size for detecting the expected effect size. Underpowered tests are the #1 cause of false negatives. (3) p-value and confidence intervals: a p-value of 0.05 means 5% chance the result is random noise. Multiple testing (checking 20 metrics) dramatically inflates false positives — use Bonferroni or Benjamini-Hochberg correction. (4) Peeking: checking results before the predetermined sample size inflates false positive rates by 2-3x. Don't peek. (5) Novelty and primacy effects: new features often get a temporary boost (novelty) or penalty (primacy) — run experiments long enough to see the steady state. (6) Network effects: in social/marketplace products, the treatment group's behavior affects the control group — need special designs (cluster randomization).

## BRANCHES
- OEC design: bad OEC = short-term clicks. Good OEC = long-term user satisfaction + revenue. If you optimize for clicks, you get clickbait. Align the OEC with the company's true north.
- Minimum detectable effect: before running the test, declare "we need a 2% improvement to ship this." Power the test to detect that effect.
- Segment analysis: overall effect = average of segments. Sometimes the feature is great for power users and bad for new users — averaging hides this. Pre-register segment hypotheses.
- Culture of experimentation: at Amazon and Microsoft, experiments are the DEFAULT way to make product decisions. No HIPPO (highest paid person's opinion) overrides a well-run experiment. Most organizations fail because experiments are optional, not required.
- Limitations: experiments tell you WHAT happened, not WHY. Pair with user research. Experiments work for incremental changes, not for discovering new product categories.

## FRUIT
- WHEN an A/B test shows a result → APPLY peeking check: was the sample size predetermined? Did anyone check results early?
- WHEN prioritizing features → APPLY the experimentation default: can you test this idea before building it fully?
- WHEN a "great idea" fails an A/B test → APPLY the 1/3 rule: most good ideas don't work. This is normal. Learn and move on.
- WHEN designing metrics → APPLY OEC alignment: is the metric you're optimizing the one that matters for the business?

## SEEDS
- "2/3 of 'good ideas' fail A/B tests. If you're not testing, you're building the wrong 2/3."
- "Don't peek at experiment results before the sample size is hit. Peeking inflates false positives."
- "Your OEC (overall evaluation criterion) must align with long-term value, not short-term clicks."
- "An experiment without a pre-registered sample size is not a valid experiment."
- "HIPPO (highest paid person's opinion) must never override a well-run experiment."

## GRAFTS
- → Superforecasting: the probabilistic thinking experiments demand.
- → Lean Analytics: the metrics that experiments improve.
- → The Lean Startup: the Build-Measure-Learn loop that experiments operationalize.
