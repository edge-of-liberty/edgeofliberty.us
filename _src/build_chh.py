#!/usr/bin/env python3
import html
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

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
SITE_URL = "https://www.edgeofliberty.us"
TOUR_URL = "https://batshitcrazyfarms.com/home/ola/services/create-happiness-house-tour"
CHH_NAME = "Create Happiness House"

ADDRESS = {
    "@type": "PostalAddress",
    "streetAddress": "154 Johnson",
    "addressLocality": "Valparaiso",
    "addressRegion": "IN",
    "postalCode": "46383",
    "addressCountry": "US",
}

PROPERTY_ADDRESS = "154 Johnson, Valparaiso, IN 46383"
PROPERTY_MAP_QUERY = "154+Johnson,+Valparaiso,+IN+46383"
MEDICAL_MAP_QUERY = "medical+facilities+near+154+Johnson,+Valparaiso,+IN+46383"


TITLE_MAP = {
    "blue": "Blue Room",
    "green": "Green Room",
    "purple": "Purple Room",
    "teal": "Teal Room",
    "common-upper": "Common Areas — Upper Level",
    "common-lower": "Common Areas — Lower Level",
    "common-other": "Common Areas — Other Spaces",
    "travel-nurse-friendly": "Travel Nurse Friendly",
}

ROOM_ORDER = ["blue", "green", "purple", "teal"]
COMMON_ORDER = ["common-upper", "common-lower", "common-other"]

ROOM_BEST_FOR = {
    "blue": "Lower-level quiet and best weekly value",
    "green": "Lower-level quiet with more space",
    "purple": "Upper-level natural light and lofted ceiling",
    "teal": "Largest room with daybed and private sitting space",
}

ROOM_FACTS = {
    "blue": ["Lower level", "Queen bed", "Desk/vanity", "TV", "Mini fridge"],
    "green": ["Lower level", "Queen bed", "Large closet", "TV", "Mini fridge"],
    "purple": ["Upper level", "Queen bed", "Lofted ceiling", "Hardwood floor", "Mini fridge"],
    "teal": ["Upper level", "Queen bed", "Daybed", "Private sitting area", "Mini fridge"],
}

AMENITIES = [
    "Furnished private bedrooms",
    "Fast WiFi",
    "On-site laundry",
    "Shared stocked kitchen",
    "On-site parking",
    "Desk in each room",
    "TV in each room",
    "Mini fridge in each room",
    "Weekly shared-space cleaning",
]

KITCHEN_STOCK_PATH = os.path.join(ROOT, "common-upper", "kitchenStock.txt")


def yaml_quote(s: str) -> str:
    if s is None:
        s = ""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def html_text(s):
    return html.escape(s or "")


def html_attr(s):
    return html.escape(s or "", quote=True)


def strip_markdown_heading(line):
    return re.sub(r"^#{1,6}\s+", "", line or "").strip()


def text_summary(text, fallback="", limit=160):
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            continue
        if line.startswith("#"):
            continue
        line = strip_markdown_heading(line)
        if line in TITLE_MAP.values() or line == CHH_NAME:
            continue
        line = re.sub(r"^[✔•*-]\s*", "", line).strip()
        if line:
            if len(line) <= limit:
                return line
            clipped = line[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
            return clipped or line[:limit]
    if len(fallback) <= limit:
        return fallback
    return fallback[:limit].rsplit(" ", 1)[0].rstrip(".,;:")


def parse_price_amounts(price):
    amounts = re.findall(r"\$(\d+(?:,\d{3})*(?:\.\d+)?)\s*/\s*(week|month)", price or "", re.I)
    parsed = {}
    for amount, unit in amounts:
        parsed[unit.lower()] = amount.replace(",", "")
    return parsed


def render_json_ld(obj):
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(obj, indent=2)
        + "\n</script>\n"
    )


def format_display_date(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return value
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


def read_availability(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []

    usable_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    raw = usable_lines[0] if usable_lines else ""
    if not raw:
        return {
            "label": "Available Now",
            "note": "Tour requests are open.",
            "schema_availability": "https://schema.org/InStock",
        }

    first_line = raw.strip()
    try:
        rented_until = date.fromisoformat(first_line)
    except ValueError:
        return {
            "label": f"Available Starting {first_line}",
            "note": "Tour requests are open for upcoming availability.",
            "schema_availability": "https://schema.org/PreOrder",
        }

    days_until_sunday = (6 - rented_until.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    available_date = rented_until + timedelta(days=days_until_sunday)

    if available_date <= date.today():
        return {
            "label": "Available Now",
            "note": "Tour requests are open.",
            "schema_availability": "https://schema.org/InStock",
        }

    return {
        "label": f"Available Starting {format_display_date(available_date.isoformat())}",
        "note": "Tour requests are open for upcoming availability.",
        "schema_availability": "https://schema.org/PreOrder",
    }


def read_kitchen_stock():
    try:
        with open(KITCHEN_STOCK_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []

    items = []
    for line in lines:
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        item = re.sub(r"^[•*-]\s*", "", item).strip()
        if "\t" in item:
            cells = [cell.strip() for cell in item.split("\t") if cell.strip()]
            item = " — ".join(cells)
        if item:
            items.append(item)
    return items


KITCHEN_STOCK = read_kitchen_stock()
DEFAULT_AVAILABILITY = read_availability("")
ROOM_AVAILABILITY = {
    slug: read_availability(os.path.join(ROOT, slug, "rentedUntil.txt"))
    for slug in ROOM_ORDER
}


def render_markdownish(text):
    lines = text.splitlines()
    out = []
    in_list = False

    for line in lines:
        line = line.rstrip()
        stripped = line.strip()

        if not stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue

        if stripped == "---":
            if in_list:
                out.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{html_text(stripped[4:].strip())}</h3>")
            continue

        if stripped.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{html_text(stripped[3:].strip())}</h2>")
            continue

        if stripped.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{html_text(stripped[2:].strip())}</h1>")
            continue

        if stripped.startswith("✔ "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<p class="chh-check-item"><strong>{html_text(stripped[2:].strip())}</strong></p>')
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html_text(stripped[2:].strip())}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{html_text(stripped)}</p>")

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

        if line == "Price" or line.startswith("Price:"):
            if line.startswith("Price:"):
                price = line.split(":", 1)[1].strip()
                i += 1
                continue
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


def render_chh_nav(current_slug=""):
    items = [
        ("", "Overview"),
        ("blue", "Blue Room"),
        ("green", "Green Room"),
        ("purple", "Purple Room"),
        ("teal", "Teal Room"),
        ("common-upper", "Upper Level"),
        ("common-lower", "Lower Level"),
        ("common-other", "Other Spaces"),
        ("travel-nurse-friendly", "Travel Nurse Friendly"),
    ]

    out = []
    out.append('<nav class="chh-subnav" aria-label="Create Happiness House pages">')
    out.append('<ul>')

    for slug, label in items:
        href = "/chh/" if slug == "" else f"/chh/{slug}/"
        cls = ' class="current"' if slug == current_slug else ""
        out.append(f'<li><a{cls} href="{html_attr(href)}">{html_text(label)}</a></li>')

    out.append('</ul>')
    out.append('</nav>')
    return "\n".join(out)


def render_cta_block():
    return (
        '<div class="chh-cta-block">\n'
        '<p><strong>Need a furnished room soon?</strong> Send a tour request and ask what is available now.</p>\n'
        f'<a class="chh-button" href="{html_attr(TOUR_URL)}">Request a Tour</a>\n'
        '</div>\n'
    )


def render_availability_badge(availability):
    return (
        '<div class="chh-availability-badge" aria-label="Rental availability">\n'
        f'<strong>{html_text(availability["label"])}</strong>\n'
        f'<span>{html_text(availability["note"])}</span>\n'
        '</div>\n'
    )


def render_kitchen_stock():
    if not KITCHEN_STOCK:
        return ""

    out = []
    out.append('<section class="chh-kitchen-stock">')
    out.append("<h2>Kitchen Stocked With</h2>")
    out.append("<p>The shared kitchen is set up for real cooking, not just reheating takeout.</p>")
    out.append("<ul>")
    for item in KITCHEN_STOCK:
        out.append(f"<li>{html_text(item)}</li>")
    out.append("</ul>")
    out.append("</section>")
    return "\n".join(out) + "\n"


def render_medical_map():
    return (
        '<section class="chh-map-section">\n'
        '<div class="chh-map-copy">\n'
        '<h2>Close to Valparaiso Medical Facilities</h2>\n'
        '<p>Create Happiness House is based at 154 Johnson in Valparaiso. The embedded map pins the property so you can see where home base is, and the links open nearby medical facilities in Google Maps.</p>\n'
        '<div class="chh-map-links">\n'
        f'<a href="https://www.google.com/maps/search/?api=1&query={PROPERTY_MAP_QUERY}" target="_blank" rel="noopener">Open Property Map</a>\n'
        f'<a href="https://www.google.com/maps/search/?api=1&query={MEDICAL_MAP_QUERY}" target="_blank" rel="noopener">Nearby Medical Facilities</a>\n'
        '</div>\n'
        '</div>\n'
        '<div class="chh-map-frame">\n'
        f'<iframe title="Map centered on Create Happiness House" src="https://www.google.com/maps?q={PROPERTY_MAP_QUERY}&output=embed" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>\n'
        '</div>\n'
        '</section>\n'
    )


def render_room_facts(slug, price=""):
    facts = ROOM_FACTS.get(slug, [])
    out = ['<div class="chh-facts">']
    if price:
        out.append(f'<div><span>Price</span><strong>{html_text(price)}</strong></div>')
    for fact in facts:
        out.append(f'<div><span>Included</span><strong>{html_text(fact)}</strong></div>')
    out.append("</div>")
    return "\n".join(out) + "\n"


def room_offer_schema(slug, display_name, price, hero_image=""):
    amounts = parse_price_amounts(price)
    price_specs = []
    if "week" in amounts:
        price_specs.append({
            "@type": "UnitPriceSpecification",
            "price": amounts["week"],
            "priceCurrency": "USD",
            "unitText": "week",
        })
    if "month" in amounts:
        price_specs.append({
            "@type": "UnitPriceSpecification",
            "price": amounts["month"],
            "priceCurrency": "USD",
            "unitText": "month",
        })

    room_url = f"{SITE_URL}/chh/{slug}/"
    item = {
        "@type": "Room",
        "name": f"{display_name} at {CHH_NAME}",
        "url": room_url,
        "containedInPlace": {"@id": f"{SITE_URL}/chh/#lodging"},
        "amenityFeature": [
            {"@type": "LocationFeatureSpecification", "name": fact, "value": True}
            for fact in ROOM_FACTS.get(slug, [])
        ],
    }
    if hero_image:
        item["image"] = f"{SITE_URL}/chh/{slug}/{hero_image}"

    offer = {
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": f"{display_name} furnished room rental",
        "url": room_url,
        "availability": "https://schema.org/InStock",
        "businessFunction": "https://schema.org/LeaseOut",
        "itemOffered": item,
    }
    if price_specs:
        offer["priceSpecification"] = price_specs
    offer["availability"] = ROOM_AVAILABILITY.get(slug, DEFAULT_AVAILABILITY)["schema_availability"]
    return offer


def lodging_schema(room_prices=None):
    room_prices = room_prices or {}
    offers = []
    for slug in ROOM_ORDER:
        display_name = TITLE_MAP[slug]
        price = room_prices.get(slug, "")
        if price:
            offers.append(room_offer_schema(slug, display_name, price))

    schema = {
        "@context": "https://schema.org",
        "@type": "LodgingBusiness",
        "@id": f"{SITE_URL}/chh/#lodging",
        "name": CHH_NAME,
        "url": f"{SITE_URL}/chh/",
        "image": f"{SITE_URL}/chh/hero.jpg",
        "description": "Furnished private rooms in a quiet shared home on a five-acre farm near Valparaiso, Indiana.",
        "address": ADDRESS,
        "areaServed": [
            {"@type": "City", "name": "Valparaiso"},
            {"@type": "AdministrativeArea", "name": "Porter County, Indiana"},
        ],
        "amenityFeature": [
            {"@type": "LocationFeatureSpecification", "name": amenity, "value": True}
            for amenity in AMENITIES
        ],
        "makesOffer": offers,
    }
    return schema


def load_room_prices():
    prices = {}
    for slug in ROOM_ORDER:
        desc_path = os.path.join(ROOT, slug, "description.txt")
        if not os.path.exists(desc_path):
            continue
        with open(desc_path, encoding="utf-8") as f:
            _, price, _, _ = parse_room_description(f.read().strip())
        if price:
            prices[slug] = price
    return prices


ROOM_PRICES = load_room_prices()


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
        f.write(f"title: {yaml_quote(f'{display_name} — Create Happiness House')}\n")
        f.write(f"og_title: {yaml_quote(f'{display_name} — Create Happiness House')}\n")

        if hero_image:
            f.write(f"image: {yaml_quote(f'/chh/{slug}/{hero_image}')}\n")
            f.write(f"og_image: {yaml_quote(f'/chh/{slug}/{hero_image}')}\n")

        if body_text:
            safe_desc = text_summary(
                body_text,
                f"Furnished private room for rent in a quiet shared home near Valparaiso, Indiana.",
            )
            f.write(f"description: {yaml_quote(safe_desc)}\n")
            f.write(f"og_description: {yaml_quote(safe_desc)}\n")

        f.write("---\n\n")

        f.write('<section class="chh-page">\n')
        f.write(render_chh_nav(slug) + "\n")
        if slug in ROOM_ORDER:
            f.write(render_json_ld(room_offer_schema(slug, display_name, price, hero_image)))
        else:
            f.write(render_json_ld(lodging_schema(ROOM_PRICES)))
        f.write(f"<h1>{html_text(display_name)}</h1>\n")

        if slug in ROOM_ORDER:
            f.write('<p class="chh-page-kicker">Furnished private room for rent in Valparaiso, Indiana</p>\n')
            f.write(render_availability_badge(ROOM_AVAILABILITY.get(slug, DEFAULT_AVAILABILITY)))
            f.write(render_room_facts(slug, price))
            f.write(render_cta_block())
        else:
            f.write(render_cta_block())

        if body_text:
            f.write(render_markdownish(body_text))

        if slug in {"common-upper", "travel-nurse-friendly"}:
            f.write("\n")
            f.write(render_kitchen_stock())

        if slug == "travel-nurse-friendly":
            f.write("\n")
            f.write(render_medical_map())

        f.write("\n")
        f.write(render_cta_block())

        if images:
            f.write("<h3>Gallery</h3>\n")
            f.write('<div class="vendor-photos constrained-gallery">\n')
            f.write('<div class="vendor-masonry">\n')
            for img in images:
                f.write(f'<img class="vendor-photo" src="{html_attr(img)}" alt="{html_attr(display_name)}">\n')
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
    f.write('title: "Furnished Rooms for Rent in Valparaiso, IN — Create Happiness House"\n')
    f.write('og_title: "Furnished Rooms for Rent in Valparaiso, IN — Create Happiness House"\n')
    f.write('description: "Furnished private rooms for rent in a quiet shared home on a five-acre farm near Valparaiso, Indiana. Weekly and monthly options available."\n')

    if hero_exists:
        f.write('image: /chh/hero.jpg\n')
        f.write('og_image: /chh/hero.jpg\n')

    f.write("---\n\n")

    f.write('<section class="chh-landing">\n')
    f.write(render_chh_nav("") + "\n")
    f.write(render_json_ld(lodging_schema(ROOM_PRICES)))
    f.write('<div class="chh-rental-hero">\n')
    f.write('<div>\n')
    f.write('<p class="chh-page-kicker">Furnished rooms for rent in Valparaiso, Indiana</p>\n')
    f.write('<h1>Create Happiness House</h1>\n')
    f.write('<p class="chh-lede">Private furnished rooms in a quiet shared home on a five-acre farm. Built for travel nurses, contract workers, remote workers, and anyone who needs a calm place to land soon.</p>\n')
    f.write('</div>\n')
    f.write('<div class="chh-hero-panel">\n')
    f.write('<strong>Available by the week or month</strong>\n')
    f.write('<span>Private room, shared home, parking, laundry, WiFi, kitchen, and outdoor space.</span>\n')
    f.write(f'<a class="chh-button" href="{html_attr(TOUR_URL)}">Request a Tour</a>\n')
    f.write('</div>\n')
    f.write('</div>\n')

    if hero_exists:
        f.write('<div class="chh-hero">\n')
        f.write('<img src="/chh/hero.jpg" alt="Create Happiness House">\n')
        f.write('</div>\n')

    if landing_text:
        f.write(render_markdownish(landing_text))

    f.write(render_kitchen_stock())

    f.write('<h2>Rooms</h2>\n')
    f.write('<div class="chh-room-grid">\n')
    for slug in ROOM_ORDER:
        name = TITLE_MAP.get(slug, slug.title())
        price = ROOM_PRICES.get(slug, "Ask for current pricing")
        f.write('<article class="chh-room-card">\n')
        f.write(f'<h3><a href="/chh/{slug}/">{html_text(name)}</a></h3>\n')
        f.write(f'<p class="chh-room-price">{html_text(price)}</p>\n')
        f.write(f'<p>{html_text(ROOM_BEST_FOR.get(slug, ""))}</p>\n')
        f.write('</article>\n')
    f.write('</div>\n')

    f.write('<h2>Common Spaces</h2>\n')
    f.write('<ul>\n')

    for slug in COMMON_ORDER:
        name = TITLE_MAP.get(slug, slug.replace("-", " ").title())
        f.write(f'<li><a href="/chh/{slug}/">{name}</a></li>\n')

    f.write('</ul>\n')

    f.write('<h2>Helpful Details</h2>\n')
    f.write('<ul>\n')
    f.write(f'<li><a href="/chh/travel-nurse-friendly/">{TITLE_MAP["travel-nurse-friendly"]}</a></li>\n')
    f.write('</ul>\n')
    f.write(render_cta_block())
    f.write('</section>\n')

print("Generated CHH landing page", file=sys.stderr)
