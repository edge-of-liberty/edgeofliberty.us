#!/usr/bin/env bash

set -e

DATA_DIR="../data"
HEADER="../partials/header.html"
FOOTER="../partials/footer.html"

for file in "$DATA_DIR"/*_vendors.txt; do
  filename=$(basename "$file")
  slug="${filename%_vendors.txt}"

  # Convert slug to display date
  # may-31-2026 → May 31, 2026
  display_date=$(echo "$slug" \
    | sed -E 's/-/ /g' \
    | sed -E 's/([a-z]+)/\u\1/g' \
    | sed -E 's/ ([0-9]{2}) / \1, /')

  outdir="../$slug"
  outfile="$outdir/index.html"

  mkdir -p "$outdir"

  {
    cat "$HEADER"
    echo "  <h2>$display_date</h2>"
    echo "  <ul>"

    while IFS= read -r vendor; do
      [[ -z "$vendor" ]] && continue
      echo "    <li>$vendor</li>"
    done < "$file"

    echo "  </ul>"
    cat "$FOOTER"
  } > "$outfile"

  echo "Generated $outfile"

done
