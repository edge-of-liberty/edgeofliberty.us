#!/usr/bin/env python3
import json
import os
import sys
import traceback

if len(sys.argv) != 3:
    print("Usage: build_home.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

try:
    ROOT = os.path.abspath(sys.argv[1])
    BUILD_JSON = sys.argv[2]

    print("[PYDEBUG] ROOT =", ROOT, file=sys.stderr)

    INCLUDES = os.path.join(ROOT, "_includes")

    with open(BUILD_JSON, encoding="utf-8") as jf:
        data = json.load(jf)

    header_path = os.path.join(INCLUDES, "header.html")
    footer_path = os.path.join(INCLUDES, "footer.html")
    intro_path = os.path.join(INCLUDES, "home_intro.html")
    dates_path = os.path.join(INCLUDES, "home_dates.html")
    vendors_path = os.path.join(INCLUDES, "home_vendors.html")
    hero_path = os.path.join(INCLUDES, "home_hero.html")

    for p in [header_path, footer_path, intro_path, dates_path, vendors_path, hero_path]:
        if not os.path.exists(p):
            raise RuntimeError(f"Missing required include: {p}")

    header_html = open(header_path, encoding="utf-8").read()
    footer_html = open(footer_path, encoding="utf-8").read()
    intro_html = open(intro_path, encoding="utf-8").read()
    dates_html = open(dates_path, encoding="utf-8").read()
    vendors_html = open(vendors_path, encoding="utf-8").read()
    hero_html = open(hero_path, encoding="utf-8").read()

    outpath = os.path.join(ROOT, "index.html")
    print("[PYDEBUG] Writing home page to:", outpath, file=sys.stderr)

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(header_html)

        f.write(hero_html)

        f.write('<section class="home-section intro-section">')
        f.write(intro_html)
        f.write('</section>')

        f.write('<section class="home-section dates-section">')
        f.write(dates_html)
        f.write('<ul class="date-list">')
        for slug, info in data["dates"].items():
            f.write(f'<li><a href="/{slug}/">{info["display"]}</a></li>')
        f.write('</ul>')
        f.write('</section>')

        f.write('<section class="home-section vendors-section">')
        f.write(vendors_html)
        f.write('<ul class="vendor-list">')
        for v in sorted(data["vendors"], key=lambda x: x["name"].lower()):
            f.write(f'<li><a href="/{v["slug"]}/">{v["name"]}</a></li>')
        f.write('</ul>')
        f.write('</section>')

        f.write(footer_html)

    if not os.path.exists(outpath):
        raise RuntimeError("Home page write failed — file does not exist")

    size = os.path.getsize(outpath)
    print("[PYDEBUG] Home page size:", size, file=sys.stderr)

    if size == 0:
        raise RuntimeError("Home page written but empty")

    print("[OK] Home page generated successfully at", outpath, file=sys.stderr)

except Exception:
    print("\n[PYERROR] Home page generation failed:", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
