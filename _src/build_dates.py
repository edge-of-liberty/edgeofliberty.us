#!/usr/bin/env python3
import html
import json
import os

import re
import sys
from datetime import date


def yaml_quote(s: str) -> str:
    """Quote a value safely for YAML front matter."""
    if s is None:
        s = ""
    # Escape backslashes and double-quotes for YAML double-quoted scalars
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def html_text(s):
    return html.escape(s or "")


def html_attr(s):
    return html.escape(s or "", quote=True)

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
ORG_URL = "https://www.edgeofliberty.us/"
GOOGLE_MAPS_PLACE_URL = "https://www.google.com/maps/place/The+Edge+of+Liberty/@41.521809,-87.036052,673m/data=!3m1!1e3!4m12!1m5!3m4!2zNDHCsDMxJzE4LjUiTiA4N8KwMDInMDkuOCJX!8m2!3d41.521809!4d-87.036052!3m5!1s0x8811992fc22aca43:0x4d56a127dde0ee9c!8m2!3d41.5215535!4d-87.0360516!16s%2Fg%2F11j78ky1z0"
BOOKING_BASE_URL = "https://batshitcrazyfarms.com/off-season-market/ols/products/the-edge-of-liberty-craft-fair-space"
BOOKING_VARIANTS = {
    "may-17-2026": "260517",
    "may-31-2026": "260531",
    "june-14-2026": "260614",
    "june-28-2026": "260628",
    "july-12-2026": "260712",
    "july-19-2026": "260719",
    "july-26-2026": "260726",
    "august-09-2026": "260809",
    "august-23-2026": "260823",
    "september-06-2026": "260906",
    "september-20-2026": "260920",
    "october-04-2026": "261004",
    "october-18-2026": "261018",
    "november-01-2026": "261101",
}
VENDOR_SPOT_LIMIT = 30
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


def slug_to_date(slug):
    ymd = slug_to_ymd(slug)
    if not ymd:
        return None
    year, month, day = ymd
    return date(year, month, day)


def date_booking_url(slug):
    variant = BOOKING_VARIANTS.get(slug)
    if not variant:
        return ""
    return f"{BOOKING_BASE_URL}/v/{variant}"


def has_food_truck(date_info):
    for vendor in date_info.get("vendors", []):
        if (vendor.get("status") or "").strip().lower() == "food truck":
            return True
    return False


def has_vendor_space(date_info):
    spots_needed = date_info.get("spots_needed")
    return isinstance(spots_needed, int) and spots_needed < VENDOR_SPOT_LIMIT


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


# Build date lists for navigation and homepage.
# Homepage shows only today/future dates; dropdown keeps past dates, moved below upcoming dates.
today = date.today()
date_links = []
upcoming_date_links = []
past_date_links = []
for slug, date_info in sorted_dates:
    event_date = slug_to_date(slug)
    if event_date is None:
        continue
    display = (date_info.get("display") or "").strip()
    link = (slug, display)
    date_links.append(link)
    if event_date < today:
        past_date_links.append(link)
    else:
        upcoming_date_links.append(link)

dropdown_date_links = upcoming_date_links + past_date_links

next_vendor_booking = None
next_food_truck_booking = None
for slug, date_info in sorted_dates:
    event_date = slug_to_date(slug)
    if event_date is None or event_date < today:
        continue

    booking_url = date_booking_url(slug)
    if not booking_url:
        continue

    display = (date_info.get("display") or "").strip()
    if next_vendor_booking is None and has_vendor_space(date_info):
        next_vendor_booking = {
            "slug": slug,
            "display": display,
            "url": booking_url,
            "spots_needed": date_info.get("spots_needed"),
        }
    if next_food_truck_booking is None and not has_food_truck(date_info):
        next_food_truck_booking = {
            "slug": slug,
            "display": display,
            "url": booking_url,
        }

    if next_vendor_booking and next_food_truck_booking:
        break

# Write the _includes/home_dates.html file (homepage date lists with Facebook links)
def write_home_date_list(f, links, list_class):
    f.write(f'<ul class="{list_class} home-date-list">\n')
    for slug, display in links:
        fb_event = facebook_events.get(slug, {})
        fb_url = fb_event.get("url")
        nd_url = fb_event.get("nextdoor")
        f.write('<li class="home-date-row">')
        f.write(f'<a class="home-date-link" href="/{html_attr(slug)}/">{html_text(display)}</a>')
        if fb_url:
            f.write(
                f'<a class="home-date-fb" href="{html_attr(fb_url)}" target="_blank" rel="noopener" aria-label="View on Facebook">'
                f'<img src="https://facebook.com/favicon.ico" alt="Facebook" class="fb-icon" loading="lazy" />'
                f'</a>'
            )
        if nd_url:
            f.write(
                f'<a class="home-date-nd" href="{html_attr(nd_url)}" target="_blank" rel="noopener" aria-label="View on Nextdoor">'
                f'<img src="https://nextdoor.com/favicon.ico" alt="Nextdoor" class="nd-icon" loading="lazy" />'
                f'</a>'
            )
        f.write('</li>\n')
    f.write('</ul>\n')


home_dates_path = os.path.join(INCLUDES, "home_dates.html")
with open(home_dates_path, "w", encoding="utf-8") as f:
    if next_vendor_booking or next_food_truck_booking:
        f.write('<div class="home-booking-actions">\n')
        if next_vendor_booking:
            f.write('<a class="home-booking-button" ')
            f.write(f'href="{html_attr(next_vendor_booking["url"])}" target="_blank" rel="noopener">')
            f.write(f'Book the Next Vendor Spot: {html_text(next_vendor_booking["display"])}</a>\n')
        if next_food_truck_booking:
            f.write('<a class="home-booking-button home-booking-button-secondary" ')
            f.write(f'href="{html_attr(next_food_truck_booking["url"])}" target="_blank" rel="noopener">')
            f.write(f'Book the Next Open Food Truck Date: {html_text(next_food_truck_booking["display"])}</a>\n')
        f.write('</div>\n')

    f.write('<div class="home-date-columns">\n')
    f.write('<div class="home-date-column home-date-column-upcoming">\n')
    f.write('<h2>Next Sundays</h2>\n')
    write_home_date_list(f, upcoming_date_links, "home-date-list-upcoming")
    f.write('</div>\n')
    if past_date_links:
        f.write('<div class="home-date-column home-date-column-past">\n')
        f.write('<h2>Market Memories</h2>\n')
        write_home_date_list(f, past_date_links, "home-date-list-past")
        f.write('</div>\n')
    f.write('</div>\n')

print(f"[OK] Wrote home dates include: {home_dates_path}", file=sys.stderr)


# Write the _includes/dates_dropdown.html file
dropdown_path = os.path.join(INCLUDES, "dates_dropdown.html")
with open(dropdown_path, "w", encoding="utf-8") as f:
    f.write('<ul class="nav-dropdown-list dates-dropdown">\n')
    for slug, display in dropdown_date_links:
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
    nd_url = facebook_events.get(slug, {}).get("nextdoor")

    event_obj = {
        "slug": slug,
        "display": display,
        "iso_date": iso_date,
        "startDate": f"{iso_date}T{START_TIME}{TZ_OFFSET}",
        "endDate": f"{iso_date}T{END_TIME}{TZ_OFFSET}",
        "url": f"/{slug}/",
        "image": f"/{slug}/hero.jpg",
        "description": EVENT_DESC,
        "hasMap": GOOGLE_MAPS_PLACE_URL
    }

    if fb_url:
        event_obj["facebook_url"] = fb_url
    if nd_url:
        event_obj["nextdoor_url"] = nd_url

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
            "@id": "https://www.edgeofliberty.us/#place"
        },
        "image": [event["image"]],
        "performer": {
            "@type": "PerformingGroup",
            "name": PERFORMER_NAME
        },
        "offers": DEFAULT_OFFER,
        "description": EVENT_DESC,
        "url": ORG_URL.rstrip("/") + event["url"],
        "hasMap": GOOGLE_MAPS_PLACE_URL,
        "organizer": {
            "@type": "Organization",
            "name": ORG_NAME,
            "url": ORG_URL,
        }
    }
    same_as = []
    if "facebook_url" in event:
        same_as.append(event["facebook_url"])
    if "nextdoor_url" in event:
        same_as.append(event["nextdoor_url"])
    if same_as:
        entry["sameAs"] = same_as
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
    event_date = date(year, month, day)
    hero_image = f"/{date_slug}/hero.jpg"

    outdir = os.path.join(ROOT, date_slug)
    os.makedirs(outdir, exist_ok=True)

    vendors = sorted(
        date_info.get("vendors", []),
        key=lambda v: (v.get("name") or "").lower()
    )

    fb_url = facebook_events.get(date_slug, {}).get("url")
    nd_url = facebook_events.get(date_slug, {}).get("nextdoor")
    booking_url = date_booking_url(date_slug)
    vendor_space_available = (
        event_date is not None
        and event_date >= today
        and booking_url
        and has_vendor_space(date_info)
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
            "@id": "https://www.edgeofliberty.us/#place"
        },
        # Per-date hero image for date pages
        "image": [hero_image],
        "performer": {
            "@type": "PerformingGroup",
            "name": PERFORMER_NAME
        },
        "offers": DEFAULT_OFFER,
        "description": EVENT_DESC,
        "hasMap": GOOGLE_MAPS_PLACE_URL,
        "organizer": {
            "@type": "Organization",
            "name": ORG_NAME,
            "url": ORG_URL,
        }
    }
    same_as = []
    if fb_url:
        same_as.append(fb_url)
    if nd_url:
        same_as.append(nd_url)
    if same_as:
        json_ld["sameAs"] = same_as

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        display = (date_info.get("display") or "").strip()

        f.write("---\n")
        f.write("layout: default\n")
        f.write(f"title: {yaml_quote(f'{EVENT_NAME} — {display}')}\n")
        f.write(f"image: {yaml_quote(hero_image)}\n")
        f.write(f"description: {yaml_quote(EVENT_DESC)}\n")
        f.write(f"og_description: {yaml_quote(EVENT_DESC)}\n")
        f.write("---\n")
        f.write("\n")

        f.write('<section class="date-page">\n')
        f.write('<div class="date-hero-row">\n')
        f.write('<div class="date-hero-text">\n')
        f.write(f"<h2>{html_text(display)}</h2>\n")
        f.write(date_intro_html)
        f.write('</div>\n')
        f.write('<div class="date-hero-media">\n')
        f.write(f'  <img class="event-hero-image" src="{html_attr(hero_image)}" alt="{html_attr(EVENT_NAME)}" loading="lazy">\n')
        f.write('</div>\n')
        f.write('</div>\n')

        f.write('<script type="application/ld+json">\n')
        f.write(json.dumps(json_ld, indent=2))
        f.write("\n</script>\n")

        f.write(f'<p><strong>Location:</strong> <a href="{GOOGLE_MAPS_PLACE_URL}" target="_blank" rel="noopener">606 N Calumet Ave, Valparaiso, IN 46383</a></p>\n')

        f.write("<p><strong>Hours:</strong> 10:00 AM – 3:00 PM (Central)</p>\n")

        if fb_url:
            f.write(f'<p><strong>Facebook event:</strong> <a href="{fb_url}" target="_blank" rel="noopener">View on Facebook</a></p>\n')
        if nd_url:
            f.write(f'<p><strong>Nextdoor event:</strong> <a href="{nd_url}" target="_blank" rel="noopener">View on Nextdoor</a></p>\n')

        if vendor_space_available:
            spots_needed = date_info.get("spots_needed")
            f.write('<div class="date-booking-card">\n')
            f.write('<div>\n')
            f.write('<h3>Vendor spaces are still available</h3>\n')
            if isinstance(spots_needed, int):
                f.write(f'<p>This date is currently at {spots_needed} of {VENDOR_SPOT_LIMIT} planned vendor spots.</p>\n')
            else:
                f.write('<p>This date is currently open for vendor booking.</p>\n')
            f.write('</div>\n')
            f.write(f'<a class="date-booking-button" href="{html_attr(booking_url)}" target="_blank" rel="noopener">Book Now</a>\n')
            f.write('</div>\n')

        if vendors:
            f.write("<h3>Vendors</h3>\n<ul>\n")
            for v in vendors:
                vslug = v.get("slug", "")
                vname = v.get("name", "")
                vstatus = (v.get("status") or "").strip().lower()
                vshort = ""

                for full in data.get("vendors", []):
                    if full.get("slug") == vslug:
                        vshort = full.get("short_description", "").strip()
                        break

                li_class = ' class="vendor-absent"' if vstatus == "absent" else ""
                f.write(f'<li{li_class}><a href="/{html_attr(vslug)}/">{html_text(vname)}</a>')

                if vshort:
                    f.write(f' — {html_text(vshort)}')

                if vstatus == "absent":
                    f.write(" <em>(unable to attend)</em>")

                f.write('</li>\n')

            f.write("</ul>\n")
        else:
            f.write("<p><em>Vendor list coming soon.</em></p>\n")

        f.write("</section>\n")

    count += 1

print(f"Generated {count} date pages", file=sys.stderr)
