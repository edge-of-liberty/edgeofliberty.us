#!/usr/bin/env python3
import os
import sys

# Build CHH pages from directory structure:
# ROOT/<slug>/{description.txt, images...}

if len(sys.argv) != 2:
    print("Usage: build_chh.py <root>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]

EXCLUDE_DIRS = {"_tmp", "_includes"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


TITLE_MAP = {
    "blue": "BLUE Room",
    "green": "GREEN Room",
    "purple": "PURPLE Room",
    "teal": "TEAL Suite",
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
        pages.append(name)
    return pages


count = 0

for slug in get_pages():
    page_dir = os.path.join(ROOT, slug)

    desc_path = os.path.join(page_dir, "description.txt")
    if not os.path.exists(desc_path):
        with open(desc_path, "w", encoding="utf-8"):
            pass

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
            f.write("<h3>Photos</h3>\n")
            f.write('<div class="chh-photos">\n')
            for img in images:
                f.write(f'<img src="/chh/{slug}/{img}" alt="{display_name}">\n')
            f.write("</div>\n")

        f.write("</section>\n")

    count += 1

print(f"Generated {count} CHH pages", file=sys.stderr)
