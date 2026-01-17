#!/usr/bin/env python3
import json
import os

import re
import sys


def yaml_quote(s: str) -> str:
    """Quote a value safely for YAML front matter."""
    if s is None:
        s = ""
    # Escape backslashes and double-quotes for YAML double-quoted scalars
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'

if len(sys.argv) != 3:
    print("Usage: build_dates.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]
BUILD_JSON = sys.argv[2]

INCLUDES = os.path.join(ROOT, "_includes")

EVENT_NAME = "The Edge of Liberty Craft Fair"
EVENT_DESC = (
    "The Edge of Liberty Craft Fair is an opportunity for local entrepreneurs "
    "to sell handmade art, crafts, and food items to their neighbors and friends "
    "in Liberty Township, Indiana."
)
ORG_NAME = "The Edge of Liberty"
ORG_URL = "https://edgeofliberty.us/"
TZ_OFFSET = "-05:00"
START_TIME = "10:00:00"
END_TIME = "15:00:00"

PERFORMER_NAME = "Open Mic Karaoke"

DEFAULT_OFFER = {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock"
}

ADDRESS = {
    "@type": "PostalAddress",
    "streetAddress": "606 N Calumet Ave",
    "addressLocality": "Valparaiso",
    "postalCode": "46383",
    "addressRegion": "IN",
    "addressCountry": "US",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

def list_vendor_images(root, slug):
    vdir = os.path.join(root, slug)
    if not os.path.isdir(vdir):
        return []
    return sorted([
        f for f in os.listdir(vdir)
        if os.path.splitext(f.lower())[1] in IMAGE_EXTS
    ])

def slug_to_ymd(slug):
    m = re.match(r"^([a-z]+)-(\d{2})-(\d{4})$", slug)
    if not m:
        return None
    mon, day, year = m.groups()
    if mon not in MONTHS:
        return None
    return (int(year), MONTHS[mon], int(day))

with open(BUILD_JSON, encoding="utf-8") as f:
    data = json.load(f)

try:
    with open(os.path.join(INCLUDES, "date_intro.html"), encoding="utf-8") as _f:
        date_intro_html = _f.read()
except FileNotFoundError:
    print(f"[WARN] Missing include: {os.path.join(INCLUDES, 'date_intro.html')} — continuing.", file=sys.stderr)
    date_intro_html = ""

sorted_dates = sorted(
    data["dates"].items(),
    key=lambda kv: slug_to_ymd(kv[0]) or (9999, 99, 99)
)

# Build a list of (slug, display) for valid date slugs, in sorted order
date_links = []
for slug, date_info in sorted_dates:
    if slug_to_ymd(slug) is None:
        continue
    display = (date_info.get("display") or "").strip()
    date_links.append((slug, display))


# Write the _includes/dates_dropdown.html file
dropdown_path = os.path.join(INCLUDES, "dates_dropdown.html")
with open(dropdown_path, "w", encoding="utf-8") as f:
    f.write('<ul class="nav-dropdown-list dates-dropdown">\n')
    for slug, display in date_links:
        f.write(f'<li><a href="/{slug}/">{display}</a></li>\n')
    f.write('</ul>\n')
print(f"[OK] Wrote dates dropdown: {dropdown_path}", file=sys.stderr)

# Write FAQ master events JSON
faq_events = []

for slug, display in date_links:
    ymd = slug_to_ymd(slug)
    if not ymd:
        continue

    year, month, day = ymd
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"

    faq_events.append({
        "slug": slug,
        "display": display,
        "iso_date": iso_date,
        "startDate": f"{iso_date}T{START_TIME}{TZ_OFFSET}",
        "endDate": f"{iso_date}T{END_TIME}{TZ_OFFSET}",
        "url": f"/{slug}/",
        "image": f"/{slug}/hero.jpg",
        "description": EVENT_DESC
    })

faq_json_path = os.path.join(INCLUDES, "faq_events.json")
with open(faq_json_path, "w", encoding="utf-8") as f:
    json.dump({"events": faq_events}, f, indent=2)

print(f"[OK] Wrote FAQ events JSON: {faq_json_path}", file=sys.stderr)

# Write SEO schema-only include for all events
faq_events_schema_path = os.path.join(INCLUDES, "faq_events_schema.html")
schema_graph = []
for event in faq_events:
    schema_graph.append({
        "@type": "Event",
        "name": EVENT_NAME,
        "startDate": event["startDate"],
        "endDate": event["endDate"],
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": ORG_NAME,
            "address": ADDRESS,
        },
        "image": [event["image"]],
        "performer": {
            "@type": "PerformingGroup",
            "name": PERFORMER_NAME
        },
        "offers": DEFAULT_OFFER,
        "description": EVENT_DESC,
        "url": ORG_URL.rstrip("/") + event["url"],
        "organizer": {
            "@type": "Organization",
            "name": ORG_NAME,
            "url": ORG_URL,
        }
    })
schema_obj = {
    "@context": "https://schema.org",
    "@graph": schema_graph
}
with open(faq_events_schema_path, "w", encoding="utf-8") as f:
    f.write('<script type="application/ld+json">\n')
    f.write(json.dumps(schema_obj, indent=2))
    f.write('\n</script>\n')
print(f"[OK] Wrote FAQ events schema HTML: {faq_events_schema_path}", file=sys.stderr)

events_schema_path = os.path.join(INCLUDES, "events_schema.json")
with open(events_schema_path, "w", encoding="utf-8") as f:
    f.write('<script type="application/ld+json">\n')
    f.write(json.dumps(schema_obj, indent=2))
    f.write('\n</script>\n')
print(f"[OK] Wrote events schema include: {events_schema_path}", file=sys.stderr)

count = 0

for date_slug, date_info in sorted_dates:
    ymd = slug_to_ymd(date_slug)
    if not ymd:
        continue

    year, month, day = ymd
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"
    hero_image = f"/{date_slug}/hero.jpg"

    outdir = os.path.join(ROOT, date_slug)
    os.makedirs(outdir, exist_ok=True)

    vendors = sorted(
        date_info.get("vendors", []),
        key=lambda v: (v.get("name") or "").lower()
    )

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": EVENT_NAME,
        "startDate": f"{iso_date}T{START_TIME}{TZ_OFFSET}",
        "endDate": f"{iso_date}T{END_TIME}{TZ_OFFSET}",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": ORG_NAME,
            "address": ADDRESS,
        },
        # Per-date hero image for date pages
        "image": [hero_image],
        "performer": {
            "@type": "PerformingGroup",
            "name": PERFORMER_NAME
        },
        "offers": DEFAULT_OFFER,
        "description": EVENT_DESC,
        "organizer": {
            "@type": "Organization",
            "name": ORG_NAME,
            "url": ORG_URL,
        }
    }

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        display = (date_info.get("display") or "").strip()

        f.write("---\n")
        f.write("layout: default\n")
        f.write(f"title: {yaml_quote(f'{EVENT_NAME} — {display}')}\n")
        f.write(f"image: {yaml_quote(hero_image)}\n")
        f.write("---\n")
        f.write("\n")

        f.write('<section class="date-page">\n')
        f.write('<div class="date-hero-row">\n')
        f.write('<div class="date-hero-text">\n')
        f.write(f"<h2>{display}</h2>\n")
        f.write(date_intro_html)
        f.write('</div>\n')
        f.write('<div class="date-hero-media">\n')
        f.write(f'  <img class="event-hero-image" src="{hero_image}" alt="{EVENT_NAME}" loading="lazy">\n')
        f.write('</div>\n')
        f.write('</div>\n')

        f.write('<script type="application/ld+json">\n')
        f.write(json.dumps(json_ld, indent=2))
        f.write("\n</script>\n")

        f.write("<p><strong>Hours:</strong> 10:00 AM – 3:00 PM (Central)</p>\n")
        f.write("<p><strong>Location:</strong> 606 N Calumet Ave, Valparaiso, IN 46383</p>\n")

        if vendors:
            f.write("<h3>Vendors</h3>\n<ul>\n")
            for v in vendors:
                vslug = v.get("slug", "")
                vname = v.get("name", "")
                vshort = ""

                for full in data.get("vendors", []):
                    if full.get("slug") == vslug:
                        vshort = full.get("short_description", "").strip()
                        break

                f.write(f'<li><a href="/{vslug}/">{vname}</a>')
                if vshort:
                    f.write(f' — {vshort}')
                f.write('</li>\n')

            f.write("</ul>\n")
        else:
            f.write("<p><em>Vendor list coming soon.</em></p>\n")

        f.write("</section>\n")

    count += 1

print(f"Generated {count} date pages", file=sys.stderr)
