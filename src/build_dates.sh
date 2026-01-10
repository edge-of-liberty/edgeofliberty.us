#!/usr/bin/env bash

set -e

DATA_DIR="../data"
HEADER="../partials/header.html"
FOOTER="../partials/footer.html"

DEFAULT_IMAGE="/images/event-default.jpg"

DESCRIPTION="The Edge of Liberty Craft Fair is an opportunity for local entrepreneurs to sell hand made art, crafts, and food items to their neighbors and friends in Liberty Township, Indiana. We're a small four acre farm just one mile north of Valparaiso committed to regenerative agriculture and community engagement where we have been celebrating life and creating happiness since 2016."

slugify() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9 ]//g' \
    | sed -E 's/ +/ /g' \
    | sed -E 's/ /-/g'
}

date_to_iso() {
  # Input: may-31-2026
  # Output: 2026-05-31

  local slug="$1"

  local month=$(echo "$slug" | cut -d- -f1)
  local day=$(echo "$slug" | cut -d- -f2)
  local year=$(echo "$slug" | cut -d- -f3)

  case "$month" in
    january)   m="01" ;;
    february)  m="02" ;;
    march)     m="03" ;;
    april)     m="04" ;;
    may)       m="05" ;;
    june)      m="06" ;;
    july)      m="07" ;;
    august)    m="08" ;;
    september) m="09" ;;
    october)   m="10" ;;
    november)  m="11" ;;
    december)  m="12" ;;
    *) echo "Unknown month: $month" && exit 1 ;;
  esac

  echo "$year-$m-$day"
}

for file in "$DATA_DIR"/*_vendors.txt; do
  filename=$(basename "$file")
  slug="${filename%_vendors.txt}"

  outdir="../$slug"
  outfile="$outdir/index.html"

  mkdir -p "$outdir"

  display_date=$(echo "$slug" \
    | sed -E 's/-/ /g' \
    | sed -E 's/([a-z]+)/\u\1/g' \
    | sed -E 's/ ([0-9]{2}) / \1, /')

  iso_date=$(date_to_iso "$slug")

  startDate="${iso_date}T10:00:00-05:00"
  endDate="${iso_date}T15:00:00-05:00"

  {
    cat "$HEADER"

    # JSON-LD
    cat <<EOF
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "The Edge of Liberty Craft Fair",
  "startDate": "$startDate",
  "endDate": "$endDate",
  "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
  "eventStatus": "https://schema.org/EventScheduled",
  "location": {
    "@type": "Place",
    "name": "The Edge of Liberty",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "606 N Calumet Ave",
      "addressLocality": "Valparaiso",
      "postalCode": "46383",
      "addressRegion": "IN",
      "addressCountry": "US"
    }
  },
  "image": [
    "https://new.edgeofliberty.us$DEFAULT_IMAGE"
  ],
  "description": "$DESCRIPTION",
  "organizer": {
    "@type": "Organization",
    "name": "The Edge of Liberty",
    "url": "https://edgeofliberty.us/"
  }
}
</script>
EOF

    echo "  <h2>$display_date</h2>"
    echo "  <ul>"

    while IFS= read -r vendor; do
      [[ -z "$vendor" ]] && continue

      vslug=$(slugify "$vendor")
      echo "    <li><a href=\"/$vslug/\">$vendor</a></li>"

    done < "$file"

    echo "  </ul>"

    cat "$FOOTER"

  } > "$outfile"

  echo "Generated $outfile"

done
