#!/usr/bin/env python3
import os
import sys

# Build CHH pages from directory structure:
# ROOT/<slug>/{description.txt, images...}

if len(sys.argv) != 2:
    print("Usage: build_chh.py <root>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]

if os.path.basename(os.path.normpath(ROOT)) != "chh":
    print(f"ERROR: build_chh.py must be run against the chh directory, got: {ROOT}", file=sys.stderr)
    sys.exit(1)

EXCLUDE_DIRS = {"_tmp", "_includes"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


TITLE_MAP = {
    "blue": "Blue Room",
    "green": "Green Room",
    "purple": "Purple Room",
    "teal": "Teal Suite",
    "common-upper": "Common Areas — Upper Level",
    "common-lower": "Common Areas — Lower Level",
    "common-other": "Common Areas — Other Spaces",
}


def render_markdownish(text):
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

    return "\n".join(out)


def get_pages():
    pages = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path):
            continue
        if name.startswith(".") or name in EXCLUDE_DIRS:
            continue
        if not os.path.exists(os.path.join(path, "description.txt")):
            continue
        pages.append(name)
    return pages


count = 0

for slug in get_pages():
    page_dir = os.path.join(ROOT, slug)

    desc_path = os.path.join(page_dir, "description.txt")
    if not os.path.exists(desc_path):
        print(f"[WARN] Skipping {slug}: missing description.txt", file=sys.stderr)
        continue

    text = ""
    with open(desc_path, encoding="utf-8") as f:
        text = f.read().strip()

    images = []
    for fn in sorted(os.listdir(page_dir)):
        if fn.startswith(".") or fn == "description.txt":
            continue
        _, ext = os.path.splitext(fn)
        if ext.lower() in IMAGE_EXTS:
            images.append(fn)

    hero_image = images[0] if images else ""
    display_name = TITLE_MAP.get(slug, slug.replace("-", " ").title())

    out_path = os.path.join(page_dir, "index.html")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f'title: "{display_name} — Create Happiness House"\n')
        f.write(f'og_title: "{display_name} — Create Happiness House"\n')

        if hero_image:
            f.write(f'image: /chh/{slug}/{hero_image}\n')
            f.write(f'og_image: /chh/{slug}/{hero_image}\n')

        if text:
            safe_desc = text.replace('"', "'").split("\n")[0][:160]
            f.write(f'description: "{safe_desc}"\n')
            f.write(f'og_description: "{safe_desc}"\n')

        f.write("---\n\n")

        f.write('<section class="chh-page">\n')
        f.write(f"<h2>{display_name}</h2>\n")

        if text:
            f.write(render_markdownish(text))

        if images:
            f.write("<h3>Gallery</h3>\n")
            f.write('<div class="vendor-photos constrained-gallery">\n')
            f.write('<div class="vendor-masonry">\n')
            for img in images:
                f.write(f'<img class="vendor-photo" src="{img}" alt="{display_name}">\n')
            f.write("</div>\n")
            f.write("</div>\n")

        f.write("</section>\n")

    count += 1


print(f"Generated {count} CHH pages", file=sys.stderr)

# Generate CHH landing page
landing_path = os.path.join(ROOT, "index.html")

with open(landing_path, "w", encoding="utf-8") as f:
    f.write("---\n")
    f.write("layout: default\n")
    f.write('title: "Create Happiness House"\n')
    f.write('og_title: "Create Happiness House"\n')
    f.write('description: "A quiet, shared home on a working farm designed for people who want space, calm, and a reset."\n')
    f.write("---\n\n")

    f.write('<section class="chh-landing">\n')
    f.write('<h1>Create Happiness House</h1>\n')

    f.write('<p>This is not a party house. It is a shared home on a working farm for people who want quiet, space, and a reset.</p>\n')

    f.write('<p>You will be sharing common areas. You will hear other humans existing. What you will not get is chaos, noise, or revolving-door short-term stays.</p>\n')

    f.write('<h2>Rooms</h2>\n')
    f.write('<ul>\n')

    room_order = ["blue", "green", "purple", "teal"]
    for slug in room_order:
        name = TITLE_MAP.get(slug, slug.title())
        f.write(f'<li><a href="/chh/{slug}/">{name}</a></li>\n')

    f.write('</ul>\n')

    f.write('<h2>Common Spaces</h2>\n')
    f.write('<ul>\n')

    common_order = ["common-upper", "common-lower", "common-other"]
    for slug in common_order:
        name = TITLE_MAP.get(slug, slug.replace("-", " ").title())
        f.write(f'<li><a href="/chh/{slug}/">{name}</a></li>\n')

    f.write('</ul>\n')

    f.write('<h2>Who This Is For</h2>\n')
    f.write('<p>People who want a calm place to land. People who can live respectfully in a shared environment. People who value quiet more than convenience.</p>\n')

    f.write('<h2>Who This Is Not For</h2>\n')
    f.write('<p>If you are looking for a party house, constant guests, or hotel-style anonymity, this is not a fit.</p>\n')

    f.write('</section>\n')

print("Generated CHH landing page", file=sys.stderr)
