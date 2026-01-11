#!/usr/bin/env python3
import json
import os
import sys

if len(sys.argv) != 3:
    print("Usage: scaffold_vendors.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]
BUILD_JSON = sys.argv[2]

VENDORS_SRC = os.path.join(ROOT, "_vendors")

with open(BUILD_JSON, encoding="utf-8") as f:
    data = json.load(f)

count = 0

for v in data["vendors"]:
    slug = v["slug"]
    vendor_dir = os.path.join(VENDORS_SRC, slug)
    os.makedirs(vendor_dir, exist_ok=True)

    desc_path = os.path.join(vendor_dir, "description.txt")
    if not os.path.exists(desc_path):
        with open(desc_path, "w", encoding="utf-8") as f:
            f.write("")  # always start empty
        print(f"Created {desc_path}", file=sys.stderr)

    count += 1

print(f"Scaffolded {count} vendor directories", file=sys.stderr)
