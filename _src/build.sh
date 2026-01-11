#!/usr/bin/env bash
set -euo pipefail
set -x

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT/_data"
VENDORS_SRC="$ROOT/_vendors"
INCLUDES="$ROOT/_includes"
IMAGES="$ROOT/_images"

YEAR=2026
CSV_FILE="$DATA_DIR/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv"

DEFAULT_EVENT_IMAGE="/_images/event-default.jpg"
BUILD_JSON="$DATA_DIR/build.json"

echo $ROOT
###############################################################################
# Utilities
###############################################################################

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g'
}

month_name() {
  case "$1" in
    jan) echo january ;;
    feb) echo february ;;
    mar) echo march ;;
    apr) echo april ;;
    may) echo may ;;
    jun) echo june ;;
    jul) echo july ;;
    aug) echo august ;;
    sep) echo september ;;
    oct) echo october ;;
    nov) echo november ;;
    dec) echo december ;;
  esac
}

###############################################################################
# CSV Parsing (via Python)
###############################################################################

parse_csv() {
python3 <<PY
import csv, json, re, sys

CSV_FILE = "${CSV_FILE}"
YEAR = 2026

def is_truthy(v):
    return (v or "").strip().upper() in ("X","Y","YES","TRUE","1")

month_map = {
    "jan":"january","feb":"february","mar":"march","apr":"april","may":"may",
    "jun":"june","jul":"july","aug":"august","sep":"september","oct":"october",
    "nov":"november","dec":"december"
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
    return {"header":h,"slug":slug,"display":display}

with open(CSV_FILE, encoding="utf-8-sig", newline="") as f:
    for _ in range(8): next(f)
    reader = csv.DictReader(f)

    date_cols = [d for h in reader.fieldnames if (d:=parse_header(h))]
    vendors = []
    dates = {d["slug"]:{"display":d["display"],"vendors":[]} for d in date_cols}

    for row in reader:
        if (row.get("2026") or "").strip() in ("","0"):
            continue

        name=(row.get("Company") or "").strip()
        if not name:
            continue

        slug=(row.get("slug") or "").strip()
        if not slug:
            slug=re.sub(r"[^a-z0-9 ]","",name.lower())
            slug=re.sub(r"\s+"," ",slug).strip().replace(" ","-")

        vendor = {
            "name": name,
            "slug": slug,
            "website": row.get("Website","").strip(),
            "store": row.get("Store","").strip(),
            "facebook": row.get("Facebook","").strip(),
            "instagram": row.get("Instagram","").strip(),
            "youtube": row.get("Youtube","").strip(),
            "public_email": row.get("Public email","").strip(),
            "public_phone": row.get("Public phone","").strip(),
            "short_description": row.get("Short Description","").strip(),
            "dates": []
        }

        for d in date_cols:
            if is_truthy(row.get(d["header"])):
                vendor["dates"].append({"slug":d["slug"],"display":d["display"]})
                dates[d["slug"]]["vendors"].append({"name":name,"slug":slug})

        vendors.append(vendor)

    print(json.dumps({"vendors":vendors,"dates":dates}))
PY
}

###############################################################################
# Markdown-ish renderer
###############################################################################

render_markdownish() {
python3 <<'PY'
import sys

text=sys.stdin.read().strip()
lines=text.splitlines()

out=[]
in_list=False

for line in lines:
    line=line.rstrip()
    if not line.strip():
        if in_list:
            out.append("</ul>")
            in_list=False
        out.append("<p></p>")
        continue

    if line.startswith("- ") or line.startswith("* "):
        if not in_list:
            out.append("<ul>")
            in_list=True
        out.append(f"<li>{line[2:].strip()}</li>")
    else:
        if in_list:
            out.append("</ul>")
            in_list=False
        out.append(f"<p>{line}</p>")

if in_list:
    out.append("</ul>")

print("\n".join(out))
PY
}

###############################################################################
# Scaffold vendor dirs
###############################################################################

scaffold_vendors() {
  echo "[INFO] Scaffolding vendor include directories..." >&2
  parse_csv > "$BUILD_JSON"
  if [[ ! -s "$BUILD_JSON" ]]; then
    echo "[ERROR] build.json missing or empty" >&2
    exit 1
  fi
  echo "[DEBUG] Using build data: $BUILD_JSON ($(wc -c < "$BUILD_JSON") bytes)" >&2
  python3 - "$BUILD_JSON" <<PY
import json, os, sys

ROOT="${ROOT}"
print("[PYDEBUG] ROOT =", ROOT)
VENDORS_SRC=os.path.join(ROOT,"_vendors")

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

count = 0
for v in data["vendors"]:
    d=os.path.join(VENDORS_SRC,v["slug"])
    os.makedirs(d,exist_ok=True)
    desc=os.path.join(d,"description.txt")
    if not os.path.exists(desc):
        with open(desc,"w") as f:
            f.write("")
        print("Created", desc)
    count += 1
print(f"Scaffolded {count} vendor include directories", file=sys.stderr)
PY
}

###############################################################################
# Build vendor pages
###############################################################################

build_vendors() {
  echo "[INFO] Generating vendor pages..." >&2
  parse_csv > "$BUILD_JSON"
  if [[ ! -s "$BUILD_JSON" ]]; then
    echo "[ERROR] build.json missing or empty" >&2
    exit 1
  fi
  echo "[DEBUG] Using build data: $BUILD_JSON ($(wc -c < "$BUILD_JSON") bytes)" >&2
  python3 - "$BUILD_JSON" <<PY
import json, os, sys

ROOT="${ROOT}"
print("[PYDEBUG] ROOT =", ROOT)
INCLUDES=os.path.join(ROOT,"_includes")
VENDORS_SRC=os.path.join(ROOT,"_vendors")

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

count = 0
for v in data["vendors"]:
    outdir=os.path.join(ROOT,v["slug"])
    os.makedirs(outdir, exist_ok=True)

    with open(os.path.join(outdir,"index.html"),"w") as f:
        f.write(open(os.path.join(INCLUDES,"header.html")).read())
        f.write("""
<style>
  body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 0; background: #f9fafb; color: #1f2937; }
  main { max-width: 960px; margin: 0 auto; padding: 2rem; }
  h1, h2, h3 { line-height: 1.25; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
  ul { padding-left: 1.25rem; }
  li { margin: 0.4rem 0; }
</style>
<main>
""")
        f.write(f"<h2>{v['name']}</h2>\n")

        src = os.path.join(VENDORS_SRC, v["slug"])
        desc = os.path.join(src, "description.txt")

        text = ""
        if os.path.exists(desc):
            with open(desc, encoding="utf-8") as df:
                text = df.read().strip()

        if not text:
            text = v.get("short_description", "").strip()

        if text:
            import subprocess, shlex, tempfile
            p = subprocess.Popen(
                ["bash", "-c", "_src/build.sh render_md"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            html, _ = p.communicate(text)
            f.write(html)

        f.write("<h3>Find us at:</h3><ul>")
        for d in v["dates"]:
            f.write(f'<li><a href="/{d["slug"]}/">{d["display"]}</a></li>')
        f.write("</ul>")

        f.write("</main>")
        f.write(open(os.path.join(INCLUDES,"footer.html")).read())
    count += 1
print(f"Generated {count} vendor pages", file=sys.stderr)
PY
}

###############################################################################
# Build date pages
###############################################################################

build_dates() {
  echo "[INFO] Generating date pages..." >&2
  parse_csv > "$BUILD_JSON"
  if [[ ! -s "$BUILD_JSON" ]]; then
    echo "[ERROR] build.json missing or empty" >&2
    exit 1
  fi
  echo "[DEBUG] Using build data: $BUILD_JSON ($(wc -c < "$BUILD_JSON") bytes)" >&2
  python3 - "$BUILD_JSON" <<PY
import json, os, re, sys

ROOT="${ROOT}"
print("[PYDEBUG] ROOT =", ROOT)
INCLUDES=os.path.join(ROOT,"_includes")

DEFAULT_EVENT_IMAGE = "/_images/event-default.jpg"
EVENT_NAME = "The Edge of Liberty Craft Fair"
EVENT_DESC = (
  "The Edge of Liberty Craft Fair is an opportunity for local entrepreneurs to sell hand made art, crafts, and food items to their neighbors and friends in Liberty Township, Indiana.  "
  "We're a small four acre farm just one mile north of Valparaiso committed to regenerative agriculture and community engagement where we have been celebrating life and creating happiness since 2016."
)
ORG_NAME = "The Edge of Liberty"
ORG_URL = "https://edgeofliberty.us/"

# Always 10–3 Central. For simplicity we emit -05:00 (matches your prior JSON-LD example).
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
  "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
  "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}

def slug_to_ymd(slug: str):
    # slug like "may-17-2026" or "october-04-2026"
    m = re.match(r"^([a-z]+)-(\d{2})-(\d{4})$", slug)
    if not m:
        return None
    mon = m.group(1)
    day = int(m.group(2))
    year = int(m.group(3))
    if mon not in MONTHS:
        return None
    return (year, MONTHS[mon], day)


with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

header_html=open(os.path.join(INCLUDES,"header.html"), encoding="utf-8").read()
footer_html=open(os.path.join(INCLUDES,"footer.html"), encoding="utf-8").read()

# Sort date slugs chronologically
sorted_dates = sorted(data["dates"].items(), key=lambda kv: slug_to_ymd(kv[0]) or (9999,99,99))

count = 0
for date_slug, date_info in sorted_dates:
    ymd = slug_to_ymd(date_slug)
    if not ymd:
        continue
    year, month, day = ymd
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"

    outdir=os.path.join(ROOT, date_slug)
    os.makedirs(outdir, exist_ok=True)

    vendors = date_info.get("vendors", [])
    # Alphabetical by vendor name for stability
    vendors_sorted = sorted(vendors, key=lambda v: (v.get("name") or "").lower())

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
      "image": [
        DEFAULT_EVENT_IMAGE
      ],
      "description": EVENT_DESC,
      "organizer": {
        "@type": "Organization",
        "name": ORG_NAME,
        "url": ORG_URL,
      }
    }

    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(header_html)
        f.write("""
<style>
  body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 0; background: #f9fafb; color: #1f2937; }
  main { max-width: 960px; margin: 0 auto; padding: 2rem; }
  h1, h2, h3 { line-height: 1.25; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
  ul { padding-left: 1.25rem; }
  li { margin: 0.4rem 0; }
</style>
<main>
""")
        f.write(f"<h2>{date_info.get('display','')}</h2>\n")
        f.write("<script type=\"application/ld+json\">\n")
        f.write(json.dumps(json_ld, ensure_ascii=False, indent=2))
        f.write("\n</script>\n")

        f.write("<p><strong>Hours:</strong> 10:00 AM – 3:00 PM (Central)</p>\n")
        f.write("<p><strong>Location:</strong> 606 N Calumet Ave, Valparaiso, IN 46383</p>\n")

        if vendors_sorted:
            f.write("<h3>Vendors</h3>\n")
            f.write("<ul>\n")
            for v in vendors_sorted:
                vslug = v.get("slug","")
                vname = v.get("name","")
                vshort = ""

                # Look up full vendor record for short description
                for full in data.get("vendors", []):
                    if full.get("slug") == vslug:
                        vshort = full.get("short_description", "").strip()
                        break

                if vshort:
                    f.write(f'<li><a href="/{vslug}/">{vname}</a> — {vshort}</li>\n')
                else:
                    f.write(f'<li><a href="/{vslug}/">{vname}</a></li>\n')
            f.write("</ul>\n")
        else:
            f.write("<p><em>Vendor list coming soon.</em></p>\n")

        f.write("</main>")
        f.write(footer_html)
    count += 1
print(f"Generated {count} date pages", file=sys.stderr)
PY
}

###############################################################################
# Build home
###############################################################################

build_home() {
  echo "[INFO] Generating home page..." >&2
  parse_csv > "$BUILD_JSON"
  if [[ ! -s "$BUILD_JSON" ]]; then
    echo "[ERROR] build.json missing or empty" >&2
    exit 1
  fi
  echo "[DEBUG] Using build data: $BUILD_JSON ($(wc -c < "$BUILD_JSON") bytes)" >&2
  python3 - "$BUILD_JSON" <<PY
import json, os, re, sys, traceback

try:
    ROOT = os.path.abspath("${ROOT}")
    print("[PYDEBUG] ROOT =", ROOT, file=sys.stderr)

    if not os.path.isdir(ROOT):
        raise RuntimeError(f"ROOT directory does not exist: {ROOT}")

    INCLUDES = os.path.join(ROOT, "_includes")
    header_path = os.path.join(INCLUDES, "header.html")
    footer_path = os.path.join(INCLUDES, "footer.html")

    print("[PYDEBUG] header path:", header_path, file=sys.stderr)
    print("[PYDEBUG] footer path:", footer_path, file=sys.stderr)

    if not os.path.exists(header_path):
        raise RuntimeError(f"Missing header: {header_path}")
    if not os.path.exists(footer_path):
        raise RuntimeError(f"Missing footer: {footer_path}")

    header_html = open(header_path, encoding="utf-8").read()
    footer_html = open(footer_path, encoding="utf-8").read()

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    MONTHS = {
      "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
      "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }

    def slug_to_ymd(slug: str):
        m = re.match(r"^([a-z]+)-(\d{2})-(\d{4})$", slug)
        if not m:
            return None
        mon = m.group(1)
        day = int(m.group(2))
        year = int(m.group(3))
        if mon not in MONTHS:
            return None
        return (year, MONTHS[mon], day)

    sorted_dates = sorted(data["dates"].items(), key=lambda kv: slug_to_ymd(kv[0]) or (9999,99,99))
    vendors_sorted = sorted(data.get("vendors", []), key=lambda v: (v.get("name") or "").lower())

    outpath = os.path.join(ROOT, "index.html")
    print("[PYDEBUG] CWD =", os.getcwd(), file=sys.stderr)
    print("[PYDEBUG] Target file =", outpath, file=sys.stderr)
    print("[PYDEBUG] Writing home page to:", outpath, file=sys.stderr)

    with open(outpath, "w", encoding="utf-8") as f:
        f.write(header_html)
        f.write("""
<style>
  body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 0; background: #f9fafb; color: #1f2937; }
  main { max-width: 960px; margin: 0 auto; padding: 2rem; }
  h1, h2, h3 { line-height: 1.25; }
  a { color: #2563eb; text-decoration: none; }
  a:hover { text-decoration: underline; }
  ul { padding-left: 1.25rem; }
  li { margin: 0.4rem 0; }
</style>
<main>
""")

        f.write("<h2>2026 Edge of Liberty Craft Fair Dates</h2>\n")
        f.write("<ul>\n")
        for date_slug, date_info in sorted_dates:
            display = date_info.get("display", date_slug)
            f.write(f'<li><a href="/{date_slug}/">{display}</a></li>\n')
        f.write("</ul>\n")

        f.write("<h2>Vendors</h2>\n")
        f.write("<ul>\n")
        for v in vendors_sorted:
            f.write(f'<li><a href="/{v.get("slug","")}/">{v.get("name","")}</a></li>\n')
        f.write("</ul>\n")

        f.write("</main>")
        f.write(footer_html)

    print("[PYDEBUG] Finished writing home page", file=sys.stderr)

    if not os.path.exists(outpath):
        raise RuntimeError("Home page write failed — file does not exist")

    size = os.path.getsize(outpath)
    print("[PYDEBUG] Home page size:", size, file=sys.stderr)

    if size == 0:
        raise RuntimeError("Home page written but empty")

    print("[OK] Home page generated successfully at", outpath, file=sys.stderr)

except Exception:
    print("\n[PYERROR] Home page generation failed:", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)
PY
}

###############################################################################
# Dispatcher
###############################################################################

case "${1:-}" in
  scaffold) scaffold_vendors ;;
  vendors) build_vendors ;;
  dates) build_dates ;;
  home) build_home ;;
  all)
    echo "[INFO] Starting full site build..." >&2
    parse_csv > "$BUILD_JSON"
    if [[ ! -s "$BUILD_JSON" ]]; then
      echo "[ERROR] build.json missing or empty" >&2
      exit 1
    fi
    echo "[DEBUG] Using build data: $BUILD_JSON ($(wc -c < "$BUILD_JSON") bytes)" >&2
    scaffold_vendors
    build_vendors
    build_dates
    build_home

    echo "[INFO] Staging all changes..."
    git add .

    if ! git diff --cached --quiet; then
      msg="Site build $(date '+%Y-%m-%d %H:%M:%S')"
      git commit -m "$msg"
      echo "[OK] Committed: $msg"

      echo "[INFO] Pushing to origin..."
      if git push; then
        echo "[OK] Push successful."
      else
        echo "[WARN] Push failed. Resolve manually." >&2
      fi
    else
      echo "[INFO] No changes to commit."
    fi

    echo "[INFO] Build complete."
    ;;
  render_md)
    render_markdownish
    ;;
  parse)
    parse_csv
    ;;
  *)
    echo "Usage: ./build.sh [all|vendors|dates|home|scaffold]"
    ;;
esac
