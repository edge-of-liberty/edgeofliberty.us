#!/usr/bin/env python3
import csv, json, re, sys
import unicodedata

if len(sys.argv) != 3:
    print("Usage: parse_csv.py <csv_file> <year>", file=sys.stderr)
    sys.exit(1)

CSV_FILE = sys.argv[1]
YEAR = int(sys.argv[2])

def is_truthy(v):
    return (v or "").strip().upper() in ("X", "Y", "YES", "TRUE", "1")

def is_hidden_vendor_name(name):
    return (name or "").strip().lower().startswith("zz")

month_map = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "may": "may", "jun": "june", "jul": "july", "aug": "august",
    "sep": "september", "oct": "october", "nov": "november", "dec": "december"
}

def slugify(s):
    if not s:
        return ""

    # Normalize unicode (strip accents, emoji, smart quotes, etc.)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")

    s = s.lower()

    # Remove ampersands explicitly
    s = s.replace("&", "")

    # Replace any non-alphanumeric sequence with a dash
    s = re.sub(r"[^a-z0-9]+", "-", s)

    # Collapse multiple dashes
    s = re.sub(r"-{2,}", "-", s)

    # Trim leading/trailing dashes
    s = s.strip("-")

    return s

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
    rows = list(csv.reader(f))

    header_row_index = 8
    spots_needed_row_index = 5
    if len(rows) <= header_row_index:
        raise SystemExit(f"CSV is missing expected header row {header_row_index + 1}")

    fieldnames = rows[header_row_index]
    spots_needed_row = rows[spots_needed_row_index] if len(rows) > spots_needed_row_index else []

    def row_cell(row, index):
        return (row[index] if index < len(row) else "").strip()

    date_cols = []
    for index, h in enumerate(fieldnames):
        parsed = parse_header(h)
        if not parsed:
            continue

        spots_needed = row_cell(spots_needed_row, index)
        parsed["spots_needed"] = int(spots_needed) if spots_needed.isdigit() else None
        date_cols.append(parsed)

    vendors = []
    dates = {
        d["slug"]: {
            "display": d["display"],
            "spots_needed": d["spots_needed"],
            "vendors": []
        }
        for d in date_cols
    }

    for raw_row in rows[header_row_index + 1:]:
        row = {
            field: row_cell(raw_row, index)
            for index, field in enumerate(fieldnames)
            if field
        }

        if (row.get(str(YEAR)) or "").strip() in ("", "0"):
            continue

        name = (row.get("Company") or "").strip()
        if not name:
            continue
        if is_hidden_vendor_name(name):
            continue

        raw_slug = (row.get("slug") or "").strip()
        if raw_slug:
            slug = slugify(raw_slug)
        else:
            slug = slugify(name)

        vendor = {
            "name": name,
            "slug": slug,
            "website": row.get("Website", "").strip(),
            "store": row.get("Store", "").strip(),
            "facebook": row.get("Facebook", "").strip(),
            "instagram": row.get("Instagram", "").strip(),
            "youtube": row.get("Youtube", "").strip(),
            "tiktok": row.get("TikTok", "").strip(),
            "public_email": row.get("Public email", "").strip(),
            "public_phone": row.get("Public phone", "").strip(),
            "short_description": row.get("Short Description", "").strip(),
            "sponsor": row.get("SPONSOR").strip(),
            "dates": []
        }

        for d in date_cols:
            cell = (row.get(d["header"]) or "").strip()
            if cell:
                vendor["dates"].append({
                    "slug": d["slug"],
                    "display": d["display"],
                    "status": cell
                })
                dates[d["slug"]]["vendors"].append({
                    "name": name,
                    "slug": slug,
                    "status": cell
                })

        vendors.append(vendor)

    print(json.dumps({"vendors": vendors, "dates": dates}, ensure_ascii=False))
