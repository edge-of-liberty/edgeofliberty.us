#!/usr/bin/env python3
"""
build_permits.py  --  Porter County "Temporary Event Coordinator Registration"
packets for The Edge of Liberty Craft Fair.

Generates one filled PDF per craft-fair date that falls within the next
WINDOW_DAYS days (Porter County asks for registration 30 days prior).

Each packet contains:
  1. Registration application, page 1 (event info + water/wastewater)
  2. Registration application, page 2 (electricity/trash/toilet/handwashing)
  3. Food Vendor Information List (food truck w/ contact details; the rest
     marked "(HBV)" -- Indiana Home Based Vendors, exempt per IC 16-42-5.3)
  4. Site map with the vendor zones outlined

Usage:  python3 build_permits.py <ROOT> <BUILD_JSON>

Output: <ROOT>/_permits/EdgeOfLiberty_TempEvent_<slug>.pdf
        (_permits/ is git-ignored: packets contain the coordinator's home
         address / phone / email and must never be published.)

Data source: build.json  ('dates' -> per-date vendor list w/ 'status';
             the food truck is the vendor whose status == "Food Truck".
             'vendors' -> contact info per vendor slug.)
"""
import io
import os
import sys
import json
from datetime import date, datetime, timedelta

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# ----------------------------------------------------------------------------
# CONFIG  --  edit these if the event details or coordinator change
# ----------------------------------------------------------------------------
WINDOW_DAYS = 30

EVENT = "The Edge of Liberty Craft Fair"
LOC   = "606 N Calumet Ave, Valparaiso, IN 46383 (Liberty Township)"
HOURS = "10:00 AM - 3:00 PM (Sunday)"
PATRONS = "200"

COORD = "Nancy Calafati"
PHONE = "219-299-9661"
EMAIL = "nancy.calafati@gmail.com"
ADDR  = "122 Philip Lane"
CITY, STATE, ZIP = "Valparaiso", "IN", "46393"

# Home-based food vendors (baked goods / jam / honey / produce). These are
# listed by name + "(HBV)" only. Add a slug here when a new food HBV joins.
HBV_FOOD_SLUGS = {
    "batshit-crazy-farms",
    "bookish-delites",
    "down-the-rabbit-hole-sourdough",
    "jens-home-goodies",
    "mommy-mustache-shop",
    "nanies-sugarbuns",
    "rues-sourdough",
    "sandy-acres-homestead",
    "the-edge-of-liberty",
}

# Known food-truck contact people (optional; keyed by vendor slug).
TRUCK_CONTACT_PERSON = {
    "las-mamacitas": "Monica",
}

# Vendor statuses that mean the vendor is NOT present that day.
NON_ATTENDING = {"Absent", "Unpaid", "Rain"}

# ----------------------------------------------------------------------------
# Coordinate helpers (template is a scanned form; coords were measured against
# a 150-dpi render: 1275 x 1651 px  ->  612 x 792 pt letter page).
# ----------------------------------------------------------------------------
PW, PH = 612.0, 792.0
IW, IH = 1275.0, 1651.0
SX, SY = PW / IW, PH / IH

def ix(x): return x * SX
def iy(y): return PH - y * SY


def overlay_page1(c, date_str, booths):
    c.setFont("Helvetica", 10)
    def t(x, y, s): c.drawString(ix(x), iy(y), s)
    t(305, 511, EVENT)
    t(312, 563, date_str)
    t(330, 614, LOC)
    t(232, 666, HOURS)
    t(452, 712, PATRONS)
    t(585, 768, str(booths))
    t(335, 824, COORD)
    t(378, 875, PHONE)
    t(872, 875, PHONE)          # cell
    t(288, 927, EMAIL)
    # fax: left blank
    t(383, 1028, ADDR)
    t(118, 1080, CITY)
    t(668, 1080, STATE)
    t(1018, 1080, ZIP)
    t(628, 1132, "Same as above (%s)" % COORD)
    t(462, 1185, PHONE)
    c.setFont("Helvetica-Bold", 11)
    def X(x, y): c.drawString(ix(x), iy(y), "X")
    X(444, 1330)   # Water: vendors must bring their own water supplies
    X(444, 1453)   # Wastewater: vendors must arrange for their own disposal


def overlay_page2(c):
    c.setFont("Helvetica", 10)
    c.drawString(ix(770), iy(92), EVENT)      # Name of Event (top)
    c.setFont("Helvetica-Bold", 11)
    def X(x, y): c.drawString(ix(x), iy(y), "X")
    X(453, 246)    # Electricity: No electricity will be supplied on site
    X(453, 338)    # Electricity: Vendors are allowed to use generators on site
    X(453, 401)    # Trash: receptacles provided throughout event for the public
    X(453, 588)    # Toilet: Portable toilets
    X(448, 736)    # Handwashing: Portable handwashing stations available
    c.setFont("Helvetica", 10)
    c.drawString(ix(810), iy(466), "Removed after each event")  # trash serviced
    c.drawString(ix(762), iy(588), "1")                         # portable toilets qty
    c.drawString(ix(810), iy(619), "Before each event")         # toilet serviced
    c.drawString(ix(600), iy(771), "1")                         # handwashing qty
    c.drawString(ix(810), iy(802), "Before each event")         # handwashing serviced


def make_vendor_page(date_str, rows, truck_note):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    m = 40
    y = PH - 50
    c.setFont("Helvetica-Bold", 15); c.drawString(m, y, "Food Vendor Information List"); y -= 26
    c.setFont("Helvetica", 10)
    c.drawString(m, y, "Temporary Event Name: %s" % EVENT); y -= 16
    c.drawString(m, y, "Location: %s" % LOC); y -= 16
    c.drawString(m, y, "Date(s): %s" % date_str); c.drawString(320, y, "Coordinator: %s" % COORD); y -= 16
    c.drawString(m, y, "Telephone: %s" % PHONE); y -= 22
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(m, y, "Food trucks are listed with full contact details. Home-based vendors are marked (HBV) and are exempt"); y -= 11
    c.drawString(m, y, "from temporary food permits under Indiana's Home Based Vendor law (IC 16-42-5.3)."); y -= 18

    x_booth, x_name, x_contact, x_phone, x_email = m, m + 55, m + 300, m + 405, m + 495
    right = PW - m
    row_h = 26
    header_y = y
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.9, 0.9, 0.9); c.rect(m, header_y - row_h + 6, right - m, row_h - 2, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    ty = header_y - 12
    c.drawString(x_booth + 3, ty, "Booth #")
    c.drawString(x_name + 3, ty, "Food Vendor Establishment Name")
    c.drawString(x_contact + 3, ty, "Contact Person")
    c.drawString(x_phone + 3, ty, "Telephone")
    c.drawString(x_email + 3, ty, "Email")

    n_rows = max(len(rows), 12)
    top = header_y - row_h + 6
    for i in range(n_rows):
        ry = top - (i + 1) * row_h
        if i < len(rows):
            name, contact, phone, email = rows[i]
            c.setFont("Helvetica", 8)
            c.drawString(x_booth + 6, ry + 8, str(i + 1))
            c.drawString(x_name + 3, ry + 8, name)
            c.drawString(x_contact + 3, ry + 8, contact)
            c.drawString(x_phone + 3, ry + 8, phone)
            c.setFont("Helvetica", 7)
            c.drawString(x_email + 3, ry + 8, email)

    c.setLineWidth(0.5)
    table_bottom = top - n_rows * row_h
    for xx in [x_booth, x_name, x_contact, x_phone, x_email, right]:
        c.line(xx, header_y + 6, xx, table_bottom)
    for i in range(n_rows + 2):
        ly = (header_y + 6) - i * row_h
        if ly >= table_bottom - 0.1:
            c.line(m, ly, right, ly)

    ny = table_bottom - 20
    c.setFont("Helvetica-Oblique", 8)
    if truck_note:
        c.drawString(m, ny, truck_note); ny -= 12
    c.drawString(m, ny, "Note: Please notify Porter County Health Department Foods Division with any additions or cancellations.")
    c.save(); buf.seek(0)
    return PdfReader(buf).pages[0]


def make_sitemap_page(sitemap_path, date_str):
    smap = PdfReader(sitemap_path).pages[0]
    w = float(smap.mediabox.width); h = float(smap.mediabox.height)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFillColorRGB(1, 1, 1); c.rect(0, h - 34, w, 34, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(8, h - 15, "Temporary Event Site Map - %s" % EVENT)
    c.setFont("Helvetica", 8)
    c.drawString(8, h - 27, "%s   |   Date: %s" % ("606 N Calumet Ave, Valparaiso, IN 46383 (Liberty Township)", date_str))
    # vendor-location callouts (page 540x720)
    c.setStrokeColorRGB(1, 0.35, 0); c.setLineWidth(2.5)
    c.rect(330, 342, 48, 30, stroke=1, fill=0)      # gravel parking area
    c.rect(214, 255, 76, 30, stroke=1, fill=0)      # open lawn area
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColorRGB(1, 1, 1)
    c.rect(330, 373, 92, 11, stroke=0, fill=1); c.rect(214, 286, 92, 11, stroke=0, fill=1)
    c.setFillColorRGB(0.85, 0.25, 0)
    c.drawString(332, 375.5, "FOOD VENDORS / BOOTHS")
    c.drawString(216, 288.5, "FOOD VENDORS / BOOTHS")
    c.setFillColorRGB(1, 1, 1); c.rect(8, 10, 320, 30, stroke=1, fill=1)
    c.setStrokeColorRGB(1, 0.35, 0); c.setFillColorRGB(0.85, 0.25, 0)
    c.rect(14, 24, 12, 9, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica", 7.5)
    c.drawString(31, 29, "Food vendor booths & food truck set up in the")
    c.drawString(31, 20, "Gravel Parking Area and the Open Lawn area (outlined).")
    c.save(); buf.seek(0)
    smap.merge_page(PdfReader(buf).pages[0])
    return smap


def build_packet(template, sitemap_path, date_str, rows, booths, truck_note, out_path):
    src = PdfReader(template)
    writer = PdfWriter()
    # application page 1 (template page index 1)
    b1 = io.BytesIO(); c1 = canvas.Canvas(b1, pagesize=letter)
    overlay_page1(c1, date_str, booths); c1.save(); b1.seek(0)
    p1 = src.pages[1]; p1.merge_page(PdfReader(b1).pages[0]); writer.add_page(p1)
    # application page 2 (template page index 2)
    b2 = io.BytesIO(); c2 = canvas.Canvas(b2, pagesize=letter)
    overlay_page2(c2); c2.save(); b2.seek(0)
    p2 = src.pages[2]; p2.merge_page(PdfReader(b2).pages[0]); writer.add_page(p2)
    # vendor list + site map
    writer.add_page(make_vendor_page(date_str, rows, truck_note))
    writer.add_page(make_sitemap_page(sitemap_path, date_str))
    with open(out_path, "wb") as f:
        writer.write(f)


def parse_display(display):
    return datetime.strptime(display, "%B %d, %Y").date()


def main():
    if len(sys.argv) < 3:
        print("Usage: build_permits.py <ROOT> <BUILD_JSON>", file=sys.stderr)
        sys.exit(1)
    root = sys.argv[1]
    build_json = sys.argv[2]
    src_dir = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(src_dir, "assets", "temp-event-packet.pdf")
    sitemap_path = os.path.join(src_dir, "assets", "site-map.pdf")
    for req in (template, sitemap_path, build_json):
        if not os.path.exists(req):
            print("[FATAL] missing required file: %s" % req, file=sys.stderr)
            sys.exit(1)

    out_dir = os.path.join(root, "_permits")
    os.makedirs(out_dir, exist_ok=True)

    data = json.load(open(build_json))
    # contact lookup by slug
    contacts = {v["slug"]: v for v in data["vendors"]}

    today = date.today()
    cutoff = today + timedelta(days=WINDOW_DAYS)

    made = []
    for slug, info in data["dates"].items():
        try:
            d = parse_display(info["display"])
        except Exception:
            continue
        if not (today <= d <= cutoff):
            continue
        date_str = info["display"]

        attending = [v for v in info["vendors"] if v["status"] not in NON_ATTENDING]
        trucks = [v for v in attending if v["status"] == "Food Truck"]
        hbv = [v for v in attending if v["slug"] in HBV_FOOD_SLUGS]

        rows = []
        for v in trucks:
            c = contacts.get(v["slug"], {})
            rows.append((v["name"],
                         TRUCK_CONTACT_PERSON.get(v["slug"], ""),
                         c.get("public_phone", ""),
                         c.get("public_email", "")))
        for v in hbv:
            rows.append(("%s (HBV)" % v["name"], "", "", ""))

        # truck note
        note = ""
        missing = [v["name"] for v in trucks
                   if not (contacts.get(v["slug"], {}).get("public_phone")
                           or contacts.get(v["slug"], {}).get("public_email"))]
        if missing:
            note = "Booth 1 (%s) is the food truck; contact info not on file - obtain from vendor." % ", ".join(missing)
        elif trucks:
            note = "Booth 1 (%s) is the food truck." % ", ".join(t["name"] for t in trucks)

        out_path = os.path.join(out_dir, "EdgeOfLiberty_TempEvent_%s.pdf" % slug)
        build_packet(template, sitemap_path, date_str, rows, len(rows), note, out_path)
        made.append((date_str, len(rows), out_path))

    if not made:
        print("[INFO] No craft-fair dates within the next %d days. Nothing to generate." % WINDOW_DAYS)
    else:
        print("[OK] Generated %d permit packet(s) in %s :" % (len(made), out_dir))
        for date_str, n, path in sorted(made):
            print("       %-20s %2d food booths  ->  %s" % (date_str, n, os.path.basename(path)))
        print("[NOTE] _permits/ is git-ignored; packets contain personal contact info and are not published.")


if __name__ == "__main__":
    main()
