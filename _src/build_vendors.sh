#!/usr/bin/env bash
set -euo pipefail

CSV_FILE="../data/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv"
HEADER="../partials/header.html"
FOOTER="../partials/footer.html"
IMAGES_DIR="../images"

python3 - "$CSV_FILE" <<'PY' > /tmp/eol_vendors.jsonl
import csv, sys, re, json

YEAR = 2026

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
    return {"header":h,"slug":slug,"display":display}

def norm_url(u):
    u=(u or "").strip()
    if not u: return ""
    if u.startswith("http://") or u.startswith("https://"): return u
    return "https://" + u

with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
    for _ in range(8): next(f)
    reader = csv.DictReader(f)

    date_cols = [d for h in reader.fieldnames if (d:=parse_header(h))]

    for row in reader:
        if (row.get("2026") or "").strip() in ("","0"): continue

        company=(row.get("Company") or "").strip()
        if not company: continue

        slug=(row.get("slug") or "").strip()
        if not slug:
            slug=re.sub(r"[^a-z0-9 ]","",company.lower())
            slug=re.sub(r"\s+"," ",slug).strip().replace(" ","-")

        dates=[]
        for d in date_cols:
            if is_truthy(row.get(d["header"])):
                dates.append({"slug":d["slug"],"display":d["display"]})
        dates.sort(key=lambda x:x["slug"])

        payload={
            "company":company,
            "slug":slug,
            "description":(row.get("Detailed Description") or "").strip(),
            "website":norm_url(row.get("Website")),
            "store":norm_url(row.get("Store")),
            "facebook":norm_url(row.get("Facebook")),
            "instagram":norm_url(row.get("Instagram")),
            "youtube":norm_url(row.get("Youtube")),
            "public_email":(row.get("Public email") or "").strip(),
            "public_phone":(row.get("Public phone") or "").strip(),
            "dates":dates
        }
        print(json.dumps(payload))
PY

while IFS= read -r line; do
  slug=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["slug"])' <<<"$line")
  company=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["company"])' <<<"$line")

  outdir="../$slug"
  mkdir -p "$outdir"

  {
    cat "$HEADER"
    echo "  <h2>$company</h2>"

    desc=$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read())["description"])' <<<"$line")
    if [[ -n "$desc" ]]; then
      echo "  <p>$desc</p>"
    fi

    echo "  <ul>"
    python3 - <<'PY' <<<"$line"
import json,sys
o=json.loads(sys.stdin.read())
def li(label,url):
    if url:
        print(f'    <li><a href="{url}" target="_blank" rel="noopener">{label}</a></li>')
li("Website",o["website"])
li("Store",o["store"])
li("Facebook",o["facebook"])
li("Instagram",o["instagram"])
li("YouTube",o["youtube"])
if o["public_email"]:
    print(f'    <li><a href="mailto:{o["public_email"]}">{o["public_email"]}</a></li>')
if o["public_phone"]:
    print(f'    <li>{o["public_phone"]}</li>')
PY
    echo "  </ul>"

    echo "  <h3>Find us at these 2026 fairs</h3>"
    echo "  <ul>"
    python3 - <<'PY' <<<"$line"
import json,sys
for d in json.loads(sys.stdin.read())["dates"]:
    print(f'    <li><a href="/{d["slug"]}/">{d["display"]}</a></li>')
PY
    echo "  </ul>"

    vendor_img_dir="$IMAGES_DIR/$slug"
    if [[ -d "$vendor_img_dir" ]]; then
      mapfile -t imgs < <(find "$vendor_img_dir" -maxdepth 1 -type f \
        \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' -o -iname '*.gif' \) | sort)
      if [[ ${#imgs[@]} -gt 0 ]]; then
        echo "  <h3>Photos</h3>"
        echo "  <div class=\"vendor-gallery\" id=\"gallery-$slug\">"
        for img in "${imgs[@]}"; do
          webpath="${img#../}"
          echo "    <img src=\"/$webpath\" alt=\"$company\">"
        done
        echo "  </div>"
        cat <<EOF
  <script>
    (function() {
      const g=document.getElementById("gallery-$slug");
      if(!g) return;
      const imgs=[...g.querySelectorAll("img")];
      for(let i=imgs.length-1;i>0;i--){
        const j=Math.floor(Math.random()*(i+1));
        g.insertBefore(imgs[j],imgs[i]);
        const t=imgs[i]; imgs[i]=imgs[j]; imgs[j]=t;
      }
    })();
  </script>
  <style>
    .vendor-gallery {
      display:grid;
      grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
      gap:12px;
      margin:12px 0 24px 0;
    }
    .vendor-gallery img {
      width:100%;
      height:auto;
      border-radius:6px;
    }
  </style>
EOF
      fi
    fi

    cat "$FOOTER"
  } > "../$slug/index.html"

  echo "Generated ../$slug/index.html"
done < /tmp/eol_vendors.jsonl
