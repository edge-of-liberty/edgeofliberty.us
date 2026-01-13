#!/usr/bin/env python3
import json
import os
import re
import sys

if len(sys.argv) != 3:
    print("Usage: build_dates.py <root> <build_json>", file=sys.stderr)
    sys.exit(1)

ROOT = sys.argv[1]
BUILD_JSON = sys.argv[2]

INCLUDES = os.path.join(ROOT, "_includes")

DEFAULT_EVENT_IMAGE = "/images/event-default.jpg"
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

header_html = open(os.path.join(INCLUDES, "header.html"), encoding="utf-8").read()
footer_html = open(os.path.join(INCLUDES, "footer.html"), encoding="utf-8").read()
date_intro_html = open(os.path.join(INCLUDES, "date_intro.html"), encoding="utf-8").read()

sorted_dates = sorted(
    data["dates"].items(),
    key=lambda kv: slug_to_ymd(kv[0]) or (9999, 99, 99)
)

count = 0

for date_slug, date_info in sorted_dates:
    ymd = slug_to_ymd(date_slug)
    if not ymd:
        continue

    year, month, day = ymd
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"

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
        # Sitewide fallback image for date pages (not vendor-specific)
        "image": [DEFAULT_EVENT_IMAGE],
        "description": EVENT_DESC,
        "organizer": {
            "@type": "Organization",
            "name": ORG_NAME,
            "url": ORG_URL,
        }
    }

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(header_html)
        f.write('<section class="date-page">\n')
        f.write('<div class="date-hero-row">\n')
        f.write('<div class="date-hero-text">\n')
        f.write(f"<h2>{date_info.get('display','')}</h2>\n")
        f.write(date_intro_html)
        f.write('</div>\n')
        f.write('<div class="date-hero-media">\n')
        f.write(f'  <img class="event-hero-image" src="{DEFAULT_EVENT_IMAGE}" alt="{EVENT_NAME}" loading="lazy">\n')
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
        f.write(footer_html)

    count += 1

print(f"Generated {count} date pages", file=sys.stderr)
