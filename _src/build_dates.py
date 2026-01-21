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

FACEBOOK_EVENTS_PATH = os.path.join(ROOT, "_data", "facebook_events.json")
try:
    with open(FACEBOOK_EVENTS_PATH, encoding="utf-8") as f:
        facebook_events = json.load(f)
except FileNotFoundError:
    print(f"[WARN] Missing Facebook events file: {FACEBOOK_EVENTS_PATH}", file=sys.stderr)
    facebook_events = {}

print(f"[OK] Loaded Facebook event links: {len(facebook_events)}", file=sys.stderr)

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
    "availability": "https://schema.org/InStock",
    "url": ORG_URL,
    "validFrom": "2026-01-01T00:00:00-05:00"
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

# Write the _includes/home_dates.html file (homepage date list with Facebook links)
home_dates_path = os.path.join(INCLUDES, "home_dates.html")
with open(home_dates_path, "w", encoding="utf-8") as f:
    f.write('<ul class="home-date-list">\n')
    for slug, display in date_links:
        fb_url = facebook_events[slug]["url"]  # assume always exists
        f.write(
            f'<li class="home-date-row">'
            f'<a class="home-date-link" href="/{slug}/">{display}</a>'
            f'<a class="home-date-fb" href="{fb_url}" target="_blank" rel="noopener" aria-label="View on Facebook">'
            f'<svg class="fb-icon" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="M22 12a10 10 0 1 0-11.5 9.9v-7h-2.2V12h2.2V9.8c0-2.2 1.3-3.4 3.3-3.4.9 0 1.9.1 1.9.1v2.1h-1.1c-1.1 0-1.4.7-1.4 1.4V12h2.4l-.4 2.9h-2v7A10 10 0 0 0 22 12z"/>'
            f'</svg>'
            f'</a>'
            f'</li>\n'
        )
    f.write('</ul>\n')

print(f"[OK] Wrote home dates include: {home_dates_path}", file=sys.stderr)


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

    fb_url = facebook_events.get(slug, {}).get("url")

    event_obj = {
        "slug": slug,
        "display": display,
        "iso_date": iso_date,
        "startDate": f"{iso_date}T{START_TIME}{TZ_OFFSET}",
        "endDate": f"{iso_date}T{END_TIME}{TZ_OFFSET}",
        "url": f"/{slug}/",
        "image": f"/{slug}/hero.jpg",
        "description": EVENT_DESC
    }

    if fb_url:
        event_obj["facebook_url"] = fb_url

    faq_events.append(event_obj)

faq_json_path = os.path.join(INCLUDES, "faq_events.json")
with open(faq_json_path, "w", encoding="utf-8") as f:
    json.dump({"events": faq_events}, f, indent=2)

print(f"[OK] Wrote FAQ events JSON: {faq_json_path}", file=sys.stderr)

# Write SEO schema-only include for all events
faq_events_schema_path = os.path.join(INCLUDES, "faq_events_schema.html")
schema_graph = []
for event in faq_events:
    entry = {
        "@type": "Event",
        "name": EVENT_NAME,
        "startDate": event["startDate"],
        "endDate": event["endDate"],
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@id": "https://edge-of-liberty.com/#place"
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
    }
    if "facebook_url" in event:
        entry["sameAs"] = [event["facebook_url"]]
    schema_graph.append(entry)
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

    fb_url = facebook_events.get(date_slug, {}).get("url")

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": EVENT_NAME,
        "startDate": f"{iso_date}T{START_TIME}{TZ_OFFSET}",
        "endDate": f"{iso_date}T{END_TIME}{TZ_OFFSET}",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@id": "https://edge-of-liberty.com/#place"
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
    if fb_url:
        json_ld["sameAs"] = [fb_url]

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

        fb_url = facebook_events.get(date_slug, {}).get("url")
        if fb_url:
            f.write(f'<p><strong>Facebook event:</strong> <a href="{fb_url}" target="_blank" rel="noopener">View on Facebook</a></p>\n')

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
