"""Integration check: what forge-brain actually injects, per turn.

Run:  python integration_check.py

Prints the real injected block for a range of messages, so the behaviour is inspectable rather
than asserted. The important property to eyeball: business-decision turns inject a category
algorithm + lenses; ordinary agent work injects NOTHING.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import __init__ as fb  # noqa: E402

CASES = [
    # (message, expect_injection)
    ("should I sign the distributor deal at these terms", True),
    ("we already invested 5 lakh in this and I know it will work", True),
    ("should we hire a second salesperson or a cofounder", True),
    ("we are in crisis and need to survive, emergency runway", True),
    ("our CAC is too high, what channel should we use", True),
    # ordinary agent work — must inject nothing
    ("read the file at notes/x.txt", False),
    ("git status", False),
    ("yes please", False),
    ("list the files in this directory", False),
    ("explain this code", False),
    ("convert this to json", False),
    ("print hello world", False),
]


def main() -> int:
    print(f"forge-brain: {len(fb.MODULES)} lenses, {len(fb._CATEGORIES)} categories\n")
    failures = 0

    for msg, expect in CASES:
        out = fb.on_pre_llm_call(user_message=msg, session_id="check")
        injected = out is not None
        ok = injected == expect
        failures += 0 if ok else 1
        tag = "INJECT " if injected else "skip   "
        mark = "ok " if ok else "FAIL"
        print(f"[{mark}] {tag} {msg!r}")
        if injected:
            block = out["context"]
            first = block.split("\n", 1)[0]
            print(f"          {first}  ({len(block)} chars)")

    print()
    # Show one full block so the output is inspectable.
    sample = fb.build_block("we already invested 5 lakh in this and I know it will work")
    print("=" * 78)
    print("FULL BLOCK for the sunk-cost case:")
    print("=" * 78)
    print(sample)
    print("=" * 78)
    print(f"\nRESULT: {'ALL CHECKS PASSED' if failures == 0 else f'{failures} FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
