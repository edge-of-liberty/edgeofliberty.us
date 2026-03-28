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


def parse_room_description(text):
    lines = text.splitlines()
    body_lines = []
    price = ""
    cta_text = ""
    cta_link = ""
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if line == "Price":
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                price = lines[i].strip()
            i += 1
            continue

        if line == "Call to Action":
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                cta_line = lines[i].strip()
                if ":" in cta_line:
                    cta_text, cta_link = cta_line.split(":", 1)
                    cta_text = cta_text.strip()
                    cta_link = cta_link.strip()
            i += 1
            continue

        body_lines.append(lines[i])
        i += 1

    body_text = "\n".join(body_lines).strip()
    return body_text, price, cta_text, cta_link


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

    body_text, price, cta_text, cta_link = parse_room_description(text)

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

        if body_text:
            safe_desc = body_text.replace('"', "'").split("\n")[0][:160]
            f.write(f'description: "{safe_desc}"\n')
            f.write(f'og_description: "{safe_desc}"\n')

        f.write("---\n\n")

        f.write('<section class="chh-page">\n')
        f.write(f"<h2>{display_name}</h2>\n")

        if body_text:
            f.write(render_markdownish(body_text))

        if price:
            f.write('<h3>Pricing</h3>\n')
            f.write(f'<p><strong>{price}</strong></p>\n')

        if cta_text and cta_link:
            f.write('<p>\n')
            f.write(f'<a href="{cta_link}">{cta_text}</a>\n')
            f.write('</p>\n')

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
landing_desc_path = os.path.join(ROOT, "description.txt")

landing_text = ""
if os.path.exists(landing_desc_path):
    with open(landing_desc_path, encoding="utf-8") as f:
        landing_text = f.read().strip()
else:
    print("[WARN] Landing page description.txt is missing in /chh", file=sys.stderr)

hero_path = os.path.join(ROOT, "hero.jpg")
hero_exists = os.path.exists(hero_path)

with open(landing_path, "w", encoding="utf-8") as f:
    f.write("---\n")
    f.write("layout: default\n")
    f.write('title: "Create Happiness House"\n')
    f.write('og_title: "Create Happiness House"\n')
    f.write('description: "A quiet, shared home on a working farm designed for people who want space, calm, and a reset."\n')

    if hero_exists:
        f.write('image: /chh/hero.jpg\n')
        f.write('og_image: /chh/hero.jpg\n')

    f.write("---\n\n")

    f.write('<section class="chh-landing">\n')
    f.write('<h1>Create Happiness House</h1>\n')

    if hero_exists:
        f.write('<div class="chh-hero">\n')
        f.write('<img src="/chh/hero.jpg" alt="Create Happiness House">\n')
        f.write('</div>\n')

    if landing_text:
        f.write(render_markdownish(landing_text))

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
    f.write('</section>\n')

print("Generated CHH landing page", file=sys.stderr)
