#!/usr/bin/env bash

set -e

DATA_DIR="../data"
HEADER="../partials/header.html"
FOOTER="../partials/footer.html"

slugify() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9 ]//g' \
    | sed -E 's/ +/ /g' \
    | sed -E 's/ /-/g'
}

# Collect and dedupe vendors
vendors=$(cat "$DATA_DIR"/*_vendors.txt \
  | sed '/^\s*$/d' \
  | sort \
  | uniq)

for vendor in $vendors; do
  # This loop will split on spaces, which we *don’t* want.
  # So we’ll do this properly below.
  :
done

# Proper line-safe loop
echo "$vendors" | while IFS= read -r vendor; do
  [[ -z "$vendor" ]] && continue

  slug=$(slugify "$vendor")
  outdir="../$slug"
  outfile="$outdir/index.html"

  mkdir -p "$outdir"

  {
    cat "$HEADER"
    echo "  <h2>$vendor</h2>"
    echo "  <p>Vendor profile coming soon.</p>"
    cat "$FOOTER"
  } > "$outfile"

  echo "Generated $outfile"

done
