#!/usr/bin/env python3
import sys

text = sys.stdin.read().strip()
lines = text.splitlines()

out = []
in_list = False

for line in lines:
    line = line.rstrip()

    if not line.strip():
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append("<p></p>")
        continue

    if line.startswith("- ") or line.startswith("* "):
        if not in_list:
            out.append("<ul>")
            in_list = True
        out.append(f"<li>{line[2:].strip()}</li>")
    else:
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p>{line}</p>")

if in_list:
    out.append("</ul>")

print("\n".join(out))
