#!/usr/bin/env python3
"""A synthetic prose policy, used to demonstrate --check-cmd.

This is deliberately small. It shows the contract: read the candidate text on
stdin, exit non-zero to refuse, print the reason on stderr. Replace the rules with
your own policy; the batch editor does not care what they are.

    python3 policy_check.py < candidate.txt
"""

import re
import sys

RULES = [
    ("em dash", re.compile("\u2014"), "Use a colon, semicolon or full stop."),
    ("hype word", re.compile(r"\b(leverage|synergy|world-class|revolutionary)\b", re.I),
     "State the concrete claim instead."),
]


def main() -> int:
    text = sys.stdin.read()
    hits = []
    for name, pattern, advice in RULES:
        for match in pattern.finditer(text):
            hits.append(f"{name}: {match.group(0)!r}. {advice}")
    if not hits:
        return 0
    print("policy check refused the text:", file=sys.stderr)
    for hit in hits:
        print(f"  {hit}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
