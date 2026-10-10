# V158 · WORKING EFFECTIVELY WITH LEGACY CODE — Michael Feathers
Tier 3 · Technology · Tree Memory

## ROOT
Legacy code is code without tests. Feathers' definition is precise and practical: if you can't change it safely and quickly, it's legacy — regardless of when it was written. The book provides a toolkit for transforming untested, tangled code into testable, maintainable code without rewriting everything. The core technique: characterization tests (tests that capture the code's CURRENT behavior before you change it), seam identification (finding points where behavior can be changed without editing the existing code), and dependency breaking (gradually extracting dependencies to make code testable).

## TRUNK
Key techniques: (1) Characterization tests: before modifying legacy code, write tests that capture what it DOES (not what it should do). These tests pass — and prove that your changes didn't break existing behavior. (2) Seam: a place where you can alter behavior without editing the code — typically through dependency injection, subclass and override, or extracting and mocking. (3) Sprout and wrap: sprout (write new code in a new method/class, test it, then call it from old code) and wrap (wrap the old code in a new method that adds behavior before/after calling the old code). (4) The legacy code algorithm: identify change points → find test points → break dependencies → write tests → make changes → refactor.

## FRUIT
- WHEN modifying old code → APPLY characterization tests: write tests for current behavior before making any change.
- WHEN code is hard to test → APPLY seam analysis: where can behavior be altered without editing the source? Extract that point.

## SEEDS
- "Legacy code = code without tests. If you can change it safely, it's not legacy."
- "Characterize current behavior before changing it. The tests you don't write are the bugs you will ship."
- "Find the seams. Change behavior without editing the existing code."

## GRAFTS
- → Accelerate: the delivery speed that legacy code slows down.
- → Continuous Delivery: the pipeline that legacy code makes impossible.
