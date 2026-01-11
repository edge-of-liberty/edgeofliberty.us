#!/usr/bin/env python3
import csv, json, re, sys

if len(sys.argv) != 3:
    print("Usage: parse_csv.py <csv_file> <year>", file=sys.stderr)
    sys.exit(1)

CSV_FILE = sys.argv[1]
YEAR = int(sys.argv[2])

def is_truthy(v):
    return (v or "").strip().upper() in ("X", "Y", "YES", "TRUE", "1")

month_map = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "may": "may", "jun": "june", "jul": "july", "aug": "august",
    "sep": "september", "oct": "october", "nov": "november", "dec": "december"
}

def parse_header(h):
    m = re.match(r"^([A-Za-z]{3})-(\d{1,2})$", h.strip())
    if not m:
        return None
    mon = month_map[m.group(1).lower()]
    day = int(m.group(2))
    d2 = f"{day:02d}"
    slug = f"{mon}-{d2}-{YEAR}"
    display = f"{mon.capitalize()} {d2}, {YEAR}"
    return {"header": h, "slug": slug, "display": display}

with open(CSV_FILE, encoding="utf-8-sig", newline="") as f:
    for _ in range(8):
        next(f)
    reader = csv.DictReader(f)

    date_cols = [d for h in reader.fieldnames if (d := parse_header(h))]
    vendors = []
    dates = {d["slug"]: {"display": d["display"], "vendors": []} for d in date_cols}

    for row in reader:
        if (row.get(str(YEAR)) or "").strip() in ("", "0"):
            continue

        name = (row.get("Company") or "").strip()
        if not name:
            continue

        slug = (row.get("slug") or "").strip()
        if not slug:
            slug = re.sub(r"[^a-z0-9 ]", "", name.lower())
            slug = re.sub(r"\s+", " ", slug).strip().replace(" ", "-")

        vendor = {
            "name": name,
            "slug": slug,
            "website": row.get("Website", "").strip(),
            "store": row.get("Store", "").strip(),
            "facebook": row.get("Facebook", "").strip(),
            "instagram": row.get("Instagram", "").strip(),
            "youtube": row.get("Youtube", "").strip(),
            "public_email": row.get("Public email", "").strip(),
            "public_phone": row.get("Public phone", "").strip(),
            "short_description": row.get("Short Description", "").strip(),
            "dates": []
        }

        for d in date_cols:
            if is_truthy(row.get(d["header"])):
                vendor["dates"].append({"slug": d["slug"], "display": d["display"]})
                dates[d["slug"]]["vendors"].append({"name": name, "slug": slug})

        vendors.append(vendor)

    print(json.dumps({"vendors": vendors, "dates": dates}, ensure_ascii=False))
