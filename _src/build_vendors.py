#!/usr/bin/env python3
import json
import os
import sys

# Expected vendor layout: ROOT/<slug>/{description.txt, image files...} — no subdirs, no copying

if len(sys.argv) != 3:
    print("Usage: build_vendors.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]
BUILD_JSON = sys.argv[2]

INCLUDES = os.path.join(ROOT, "_includes")

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

with open(BUILD_JSON, encoding="utf-8") as f:
    data = json.load(f)

header_html = open(os.path.join(INCLUDES, "header.html"), encoding="utf-8").read()
footer_html = open(os.path.join(INCLUDES, "footer.html"), encoding="utf-8").read()

count = 0

for v in data["vendors"]:
    slug = v["slug"]
    name = v["name"]

    outdir = os.path.join(ROOT, slug)
    os.makedirs(outdir, exist_ok=True)

    # Images and description live directly in ROOT/<slug>/ — no duplication, no copying
    src_dir = outdir

    images = []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    if os.path.isdir(src_dir):
        for fn in sorted(os.listdir(src_dir)):
            if fn.startswith("."):
                continue
            if fn.lower() == "description.txt":
                continue

            _, ext = os.path.splitext(fn)
            if ext.lower() in exts:
                images.append(fn)

    # Description
    desc_path = os.path.join(src_dir, "description.txt")
    text = ""
    if os.path.exists(desc_path):
        with open(desc_path, encoding="utf-8") as f:
            text = f.read().strip()

    if not text:
        text = v.get("short_description", "").strip()

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(header_html)
        f.write('<section class="vendor-page">\n')
        f.write(f"<h2>{name}</h2>\n")

        # Dates section moved here
        f.write('<div class="vendor-dates">\n')
        f.write("<h3>Craft Fair Dates</h3>\n<ul>\n")
        for d in sorted(v["dates"], key=lambda x: x.get("display", "")):
            f.write(f'<li><a href="/{d["slug"]}/">{d["display"]}</a></li>\n')
        f.write("</ul>\n")
        f.write("</div>\n")

        f.write('<div class="vendor-content">\n')

        if text:
            f.write(render_markdownish(text))

        # Contact & Links block
        contact_fields = [
            ("website", ""),
            ("store", ""),
            ("facebook", ""),
            ("instagram", ""),
            ("youtube", ""),
            ("public_email", "mailto:"),
            ("public_phone", "tel:"),
        ]
        links = []
        for field, prefix in contact_fields:
            val = v.get(field, "").strip()
            if val:
                if field == "public_email":
                    links.append(f'<li><a href="mailto:{val}">Email</a></li>')
                elif field == "public_phone":
                    links.append(f'<li><a href="tel:{val}">Phone</a></li>')
                else:
                    links.append(f'<li><a href="{val}">{field.capitalize()}</a></li>')

        if links:
            f.write("<h3>Contact & Links</h3>\n")
            f.write("<ul>\n")
            for link in links:
                f.write(link + "\n")
            f.write("</ul>\n")
        else:
            f.write('<p class="vendor-inperson-only">This vendor currently sells in person at our craft fairs only.</p>\n')

        # Photos section
        if images:
            f.write("<h3>Gallery</h3>\n")
            f.write('<div class="vendor-photos constrained-gallery">\n')
            f.write('<div class="vendor-masonry">\n')
            for img in images:
                src = img
                f.write(f'<img class="vendor-photo" src="{src}" alt="{name}">\n')
            f.write("</div>\n")
            f.write("</div>\n")

        f.write("</div>\n")

        f.write("</section>\n")
        f.write(footer_html)

    count += 1

print(f"Generated {count} vendor pages", file=sys.stderr)
