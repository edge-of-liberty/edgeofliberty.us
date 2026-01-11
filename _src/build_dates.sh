#!/usr/bin/env bash
set -euo pipefail

CSV_FILE="../data/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv"
HEADER="../partials/header.html"
FOOTER="../partials/footer.html"

DEFAULT_IMAGE_PATH="/images/event-default.jpg"
BASE_DOMAIN="https://new.edgeofliberty.us"

DESCRIPTION="The Edge of Liberty Craft Fair is an opportunity for local entrepreneurs to sell hand made art, crafts, and food items to their neighbors and friends in Liberty Township, Indiana. We're a small four acre farm just one mile north of Valparaiso committed to regenerative agriculture and community engagement where we have been celebrating life and creating happiness since 2016."

python3 - "$CSV_FILE" <<'PY' > /tmp/eol_dates.jsonl
import csv, sys, re, json
from datetime import datetime
from zoneinfo import ZoneInfo

YEAR = 2026
TZ = "America/Chicago"

def is_truthy(v):
    v=(v or "").strip().upper()
    return v in ("X","Y","YES","TRUE","1")

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
    iso = f"{YEAR}-{list(month_map.values()).index(mon)+1:02d}-{d2}"
    return {"header":h,"slug":slug,"display":display,"iso":iso}

with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
    for _ in range(8): next(f)
    reader = csv.DictReader(f)
    date_cols = [d for h in reader.fieldnames if (d:=parse_header(h))]
    date_map = {d["slug"]:{"date":d,"vendors":[]} for d in date_cols}

    for row in reader:
        if (row.get("2026") or "").strip() in ("","0"): continue
        company=(row.get("Company") or "").strip()
        if not company: continue
        slug=(row.get("slug") or "").strip()
        if not slug:
            slug=re.sub(r"[^a-z0-9 ]","",company.lower())
            slug=re.sub(r"\s+"," ",slug).strip().replace(" ","-")

        for d in date_cols:
            if is_truthy(row.get(d["header"])):
                date_map[d["slug"]]["vendors"].append({"name":company,"slug":slug})

    for k,v in date_map.items():
        v["vendors"].sort(key=lambda x:x["name"].lower())
        print(json.dumps(v))
PY

while IFS= read -r line; do
  slug=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["date"]["slug"])' <<<"$line")
  display=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["date"]["display"])' <<<"$line")
  iso=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["date"]["iso"])' <<<"$line")

  start=$(python3 - <<PY
from datetime import datetime
from zoneinfo import ZoneInfo
dt=datetime.fromisoformat("$iso"+"T10:00:00").replace(tzinfo=ZoneInfo("America/Chicago"))
print(dt.isoformat(timespec="seconds"))
PY
)

  end=$(python3 - <<PY
from datetime import datetime
from zoneinfo import ZoneInfo
dt=datetime.fromisoformat("$iso"+"T15:00:00").replace(tzinfo=ZoneInfo("America/Chicago"))
print(dt.isoformat(timespec="seconds"))
PY
)

  outdir="../$slug"
  mkdir -p "$outdir"

  {
    cat "$HEADER"
    cat <<EOF
<script type="application/ld+json">
{
  "@context":"https://schema.org",
  "@type":"Event",
  "name":"The Edge of Liberty Craft Fair",
  "startDate":"$start",
  "endDate":"$end",
  "eventAttendanceMode":"https://schema.org/OfflineEventAttendanceMode",
  "eventStatus":"https://schema.org/EventScheduled",
  "location":{
    "@type":"Place",
    "name":"The Edge of Liberty",
    "address":{
      "@type":"PostalAddress",
      "streetAddress":"606 N Calumet Ave",
      "addressLocality":"Valparaiso",
      "postalCode":"46383",
      "addressRegion":"IN",
      "addressCountry":"US"
    }
  },
  "image":["$BASE_DOMAIN$DEFAULT_IMAGE_PATH"],
  "description":"$DESCRIPTION"
}
</script>
EOF
    echo "  <h2>$display</h2>"
    echo "  <ul>"
    python3 - <<'PY' <<<"$line"
import json,sys
for v in json.loads(sys.stdin.read())["vendors"]:
    print(f'    <li><a href="/{v["slug"]}/">{v["name"]}</a></li>')
PY
    echo "  </ul>"
    cat "$FOOTER"
  } > "../$slug/index.html"

  echo "Generated ../$slug/index.html"
done < /tmp/eol_dates.jsonl
