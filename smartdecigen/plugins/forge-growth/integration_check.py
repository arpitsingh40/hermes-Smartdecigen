"""Integration check: what forge-growth actually injects, per turn.

Run:  python integration_check.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fg  # noqa: E402

CASES = [
    ("our revenue is dropping and sales are flat", True),
    ("customers are churning, we keep losing them", True),
    ("we are running out of money, burn rate too high", True),
    ("growth has stalled, how do we 10x", True),
    ("how do we grow this business", True),
    ("read the file at notes/x.txt", False),
    ("what is the capital of France", False),
    ("git status", False),
    ("fix the typo in line 42", False),
]


def main() -> int:
    print(f"forge-growth: {len(fg.DEPENDENCY_GRAPH)} functions, "
          f"{len(fg._SYMPTOMS)} symptom patterns\n")
    fails = 0
    for msg, expect in CASES:
        out = fg.on_pre_llm_call(user_message=msg)
        got = out is not None
        ok = got == expect
        fails += 0 if ok else 1
        print(f"[{'ok ' if ok else 'FAIL'}] {'INJECT' if got else 'skip  '} {msg!r}")
        if got:
            sections = [s.split("(")[0].split("—")[0].strip()
                        for s in out["context"].split("\n\n") if s.strip()]
            print(f"          {len(out['context'])} chars | {sections}")

    print()
    for probe, title in [
        ("our revenue is dropping and sales are flat", "PROBLEM TURN (diagnosis first)"),
        ("growth has stalled, how do we 10x", "GROWTH TURN (plan first)"),
    ]:
        print("=" * 78)
        print(title)
        print("=" * 78)
        print(fg.build_block(probe))
        print()

    print(f"RESULT: {'ALL CHECKS PASSED' if fails == 0 else f'{fails} FAILURES'}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
