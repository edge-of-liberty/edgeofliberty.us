#!/usr/bin/env python3
import html
import json
import os
import sys

# Expected vendor layout: ROOT/<slug>/{description.txt, image files...} — no subdirs, no copying

if len(sys.argv) != 3:
    print("Usage: build_vendors.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]
BUILD_JSON = sys.argv[2]


def yaml_quote(s: str) -> str:
    if s is None:
        s = ""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def html_text(s):
    return html.escape(s or "")


def html_attr(s):
    return html.escape(s or "", quote=True)


SITE_BASE = "https://www.edgeofliberty.us"
VENUE_CITY = "Valparaiso"
VENUE_REGION = "IN"


def clean_truncate(s, limit):
    """Collapse whitespace and truncate on a word boundary (never mid-word)."""
    s = " ".join((s or "").split())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:—-")


def build_title(name, short_desc):
    """Keyword- and location-rich <title>, e.g.
    'Down The Rabbit Hole Sourdough – Artisan sourdough breads | Valparaiso, IN'."""
    if short_desc:
        base = clean_truncate(f"{name} – {short_desc}", 60)
        return f"{base} | {VENUE_CITY}, {VENUE_REGION}"
    return f"{name} | The Edge of Liberty Craft Fair, {VENUE_CITY} {VENUE_REGION}"


def build_meta_description(text, short_desc, name):
    """Clean, sentence-safe meta description with product + location, never cut mid-word."""
    base = (text.split("\n")[0].strip() if text else "") or short_desc or name
    suffix = f" Find {name} at The Edge of Liberty Craft Fair in {VENUE_CITY}, {VENUE_REGION}."
    base = clean_truncate(base, max(40, 157 - len(suffix)))
    if base and base[-1] not in ".!?":
        base += "."
    return (base + suffix).strip()


def vendor_jsonld(v, name, slug, hero_image, desc):
    """Organization + breadcrumb structured data so search engines recognize the vendor."""
    url = f"{SITE_BASE}/{slug}/"
    org = {"@type": "Organization", "@id": url + "#org", "name": name, "url": url}
    if desc:
        org["description"] = clean_truncate(desc, 300)
    if hero_image:
        org["image"] = f"{SITE_BASE}/{slug}/{hero_image}"
    same_as = [
        (v.get(field) or "").strip()
        for field in ("website", "store", "facebook", "instagram", "youtube", "tiktok")
        if (v.get(field) or "").strip().startswith("http")
    ]
    if same_as:
        org["sameAs"] = same_as
    if (v.get("public_phone") or "").strip():
        org["telephone"] = v["public_phone"].strip()
    if (v.get("public_email") or "").strip():
        org["email"] = v["public_email"].strip()
    org["areaServed"] = {"@type": "City", "name": f"{VENUE_CITY}, Indiana"}
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": name, "item": url},
        ],
    }
    graph = {"@context": "https://schema.org", "@graph": [org, breadcrumb]}
    return '<script type="application/ld+json">\n' + json.dumps(graph, indent=2, ensure_ascii=False) + "\n</script>\n"


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
            out.append(f"<li>{html_text(line[2:].strip())}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{html_text(line)}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


with open(BUILD_JSON, encoding="utf-8") as f:
    data = json.load(f)
    print("[DEBUG] Total vendors:", len(data.get("vendors", [])), file=sys.stderr)
    for v in data.get("vendors", []):
        print("[DEBUG] RAW sponsor field for", v.get("name"), "=>", repr(v.get("sponsor")), type(v.get("sponsor")), file=sys.stderr)

regular_vendors = [v for v in data["vendors"] if not (v.get("sponsor") or "").strip()]
sponsors = [v for v in data["vendors"] if (v.get("sponsor") or "").strip()]
print("[DEBUG] Regular vendors:", [v.get("name") for v in regular_vendors], file=sys.stderr)
print("[DEBUG] Sponsors:", [v.get("name") for v in sponsors], file=sys.stderr)

# Scaffold step: ensure directories and description.txt for regular vendors
for v in regular_vendors:
    slug = v["slug"]
    outdir = os.path.join(ROOT, slug)
    os.makedirs(outdir, exist_ok=True)
    desc_path = os.path.join(outdir, "description.txt")
    if not os.path.exists(desc_path):
        with open(desc_path, "w", encoding="utf-8") as f:
            pass
    print(f"[DEBUG] Scaffolded vendor dir: {slug}", file=sys.stderr)

# Generate vendors dropdown include (alphabetical, scrollable)
includes_dir = os.path.join(ROOT, "_includes")
os.makedirs(includes_dir, exist_ok=True)

dropdown_path = os.path.join(includes_dir, "vendors_dropdown.html")

sorted_vendors = sorted(regular_vendors, key=lambda v: v["name"].lower())

with open(dropdown_path, "w", encoding="utf-8") as df:
    df.write('<div class="dropdown-menu dropdown-scroll">\n')
    df.write('<a href="https://batshitcrazyfarms.com/off-season-market/ols/products/the-edge-of-liberty-craft-fair-space" target="_top" rel="noopener">Become a Vendor</a>\n')
    df.write('<div class="dropdown-divider"></div>\n')
    for v in sorted_vendors:
        df.write(f'<a href="/{html_attr(v["slug"])}/">{html_text(v["name"])}</a>\n')
    df.write('</div>\n')

# Generate home_vendors.html include (intro + list)
home_vendors_path = os.path.join(includes_dir, "home_vendors.html")

with open(home_vendors_path, "w", encoding="utf-8") as hf:
    hf.write("<h2>Look Who’s Attending</h2>\n")
    hf.write("<p>Here’s who you’ll find at our upcoming craft fairs:</p>\n")
    hf.write('<div class="home-vendor-list">\n')
    for v in sorted_vendors:
        name = v["name"]
        slug = v["slug"]
        short_desc = (v.get("short_description") or "").strip()

        if short_desc:
            hf.write(f'<p><a href="/{html_attr(slug)}/">{html_text(name)}</a> — {html_text(short_desc)}</p>\n')
        else:
            hf.write(f'<p><a href="/{html_attr(slug)}/">{html_text(name)}</a></p>\n')
    hf.write('</div>\n')

count = 0

for v in regular_vendors:
    slug = v["slug"]
    name = v["name"]

    outdir = os.path.join(ROOT, slug)
    # No directory creation here; scaffold step already ensured it

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

    # Primary image for OG / social sharing (first alphabetically)
    hero_image = images[0] if images else ""

    # Description sources
    desc_path = os.path.join(src_dir, "description.txt")
    file_text = ""
    if os.path.exists(desc_path):
        with open(desc_path, encoding="utf-8") as f:
            file_text = f.read().strip()

    short_desc = (v.get("short_description") or "").strip()
    body_text = file_text or short_desc
    lead_source = short_desc or (body_text.split("\n")[0].strip() if body_text else "")

    page_title = build_title(name, short_desc)
    meta_desc = build_meta_description(short_desc or file_text, short_desc, name)
    img_alt = clean_truncate(f"{name} – {short_desc}", 110) if short_desc else name

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write("layout: default\n")
        f.write(f"title: {yaml_quote(page_title)}\n")
        f.write(f"og_title: {yaml_quote(page_title)}\n")

        # OG / social metadata (used by layout)
        if hero_image:
            f.write(f"image: {yaml_quote(f'/{slug}/{hero_image}')}\n")
            f.write(f"og_image: {yaml_quote(f'/{slug}/{hero_image}')}\n")

        if meta_desc:
            f.write(f"description: {yaml_quote(meta_desc)}\n")
            f.write(f"og_description: {yaml_quote(meta_desc)}\n")

        f.write("---\n\n")

        # Structured data: identify the vendor as an Organization + breadcrumb
        f.write(vendor_jsonld(v, name, slug, hero_image, lead_source))

        f.write('<section class="vendor-page">\n')
        f.write(f"<h1>{html_text(name)}</h1>\n")

        f.write('<div class="vendor-content">\n')

        # SEO lead line: product + location keywords as real, crawlable body copy
        if lead_source:
            lead = (
                f"{html_text(lead_source)} — find {html_text(name)} at The Edge of Liberty "
                f"Craft Fair in {VENUE_CITY}, {VENUE_REGION} (Northwest Indiana)."
            )
            f.write(f'<p class="vendor-lead">{lead}</p>\n')

        # Vendor's own write-up (only when it adds copy beyond the one-line description)
        if file_text and file_text.strip() != short_desc:
            f.write(render_markdownish(file_text))

        # Contact & Links block
        contact_fields = [
            ("website", ""),
            ("store", ""),
            ("facebook", ""),
            ("instagram", ""),
            ("youtube", ""),
            ("tiktok", ""),
            ("public_email", "mailto:"),
            ("public_phone", "tel:"),
        ]
        links = []
        for field, prefix in contact_fields:
            val = (v.get(field) or "").strip()
            if val:
                if field == "public_email":
                    links.append(f'<li><a href="mailto:{html_attr(val)}">Email</a></li>')
                elif field == "public_phone":
                    links.append(f'<li><a href="tel:{html_attr(val)}">Phone</a></li>')
                else:
                    links.append(f'<li><a href="{html_attr(val)}">{html_text(field.capitalize())}</a></li>')

        if links:
            f.write("<h3>Contact & Links</h3>\n")
            f.write("<ul>\n")
            for link in links:
                f.write(link + "\n")
            f.write("</ul>\n")
        else:
            f.write('<p class="vendor-inperson-only">This vendor currently sells in person at our craft fairs only.</p>\n')

        # Dates (preserve CSV column order)
        f.write('<div class="vendor-dates">\n')
        f.write("<h3>Find us at these craft fair dates</h3>\n<ul>\n")
        for d in v.get("dates", []):
            # Do NOT sort; parse_csv.py already appends in CSV column order.
            # Show the date link regardless of the per-date status value.
            f.write(f'<li><a href="/{html_attr(d["slug"])}/">{html_text(d["display"])}</a></li>\n')
        f.write("</ul>\n")
        f.write("</div>\n")

        # Photos section
        if images:
            f.write("<h3>Gallery</h3>\n")
            f.write('<div class="vendor-photos constrained-gallery">\n')
            f.write('<div class="vendor-masonry">\n')
            for img in images:
                src = img
                f.write(f'<img class="vendor-photo" src="{html_attr(src)}" alt="{html_attr(img_alt)}" loading="lazy">\n')
            f.write("</div>\n")
            f.write("</div>\n")

        f.write("</div>\n")

        f.write("</section>\n")

    count += 1

print(f"Generated {count} vendor pages", file=sys.stderr)

# Generate sponsors.html page
sponsors_path = os.path.join(ROOT, "sponsors.html")
with open(sponsors_path, "w", encoding="utf-8") as sf:
    sf.write("---\n")
    sf.write("layout: default\n")
    sf.write('title: "Sponsors"\n')
    sf.write("---\n\n")

    sf.write('<section class="sponsors-page">\n')
    sf.write('{% include sponsor_intro.html %}\n')
    sf.write('<table class="sponsors-table">\n')

    # Hidden header row for accessibility / alignment
    sf.write('<thead style="display:none;">\n')
    sf.write("<tr>\n")
    sf.write("<th>Company</th>\n")
    sf.write("<th>Link</th>\n")
    sf.write("<th>Contact</th>\n")
    sf.write("<th>Proof</th>\n")
    sf.write("</tr>\n")
    sf.write("</thead>\n")

    sf.write("<tbody>\n")

    for v in sponsors:
        name = (v.get("name") or "").strip()
        website = (v.get("website") or "").strip()
        facebook = (v.get("facebook") or "").strip()
        contact_email = (v.get("public_email") or "").strip()
        contact_phone = (v.get("public_phone") or "").strip()
        slug = (v.get("slug") or "").strip()

        # Determine website or facebook cell
        site_link = website if website else (facebook if facebook else "")

        # Determine public contact cell
        contact = contact_email if contact_email else (contact_phone if contact_phone else "")

        sf.write("<tr>\n")

        # Company
        sf.write(f'<td class="sponsor-name">{name}</td>\n')

        # Website / Facebook
        if site_link:
            label = "Facebook" if "facebook.com" in site_link.lower() else "Visit site"
            sf.write(f'<td class="sponsor-link"><a href="{site_link}" target="_blank" rel="noopener">{label}</a></td>\n')
        else:
            sf.write('<td class="sponsor-link"></td>\n')

        # Contact
        if contact:
            if contact_email:
                sf.write(f'<td class="sponsor-contact"><a href="mailto:{contact}">Email</a></td>\n')
            elif contact_phone:
                sf.write(f'<td class="sponsor-contact"><a href="tel:{contact}">Call</a></td>\n')
            else:
                sf.write(f'<td class="sponsor-contact">{contact}</td>\n')
        else:
            sf.write('<td class="sponsor-contact"></td>\n')

        # Proof link
        proof_link = f"/proof/{slug}.pdf"
        sf.write(f'<td class="sponsor-proof"><a href="{proof_link}" title="View sign proof" aria-label="View sign proof">📋</a></td>\n')

        sf.write("</tr>\n")

    sf.write("</tbody>\n")
    sf.write("</table>\n")
    sf.write("</section>\n")
