# edgeofliberty.us

Website sources and shared build tooling for Edge of Liberty and Create Happiness House.

## Normal publishing workflow

From this repository, run:

```bash
./_src/build.sh all
```

This builds the existing Edge of Liberty content (including local permit packets),
its `/chh/` pages, and the standalone CHH site, then commits and pushes website
changes in each repository independently. An unchanged repository is successful;
pending commits are still pushed. If one publication fails, the other is attempted
and the command exits with an error identifying the failed site. Run again to retry.
All builds finish before publishing begins. The two remote pushes are not atomic.

The standalone checkout defaults to `../createhappinesshouse.com`. Override with
`CHH_REPO=/path/to/createhappinesshouse.com` or `--chh-repo /path/to/createhappinesshouse.com`.
Git commands always address the selected repository explicitly.

## One editable CHH source

Edit descriptions, prices, `rentedUntil.txt`, kitchen inventory, and photos only in
`chh/` in **this** repository. Both outputs use those files and the same build date.
Availability follows the existing rule: the Sunday strictly after the rented-until
date, changing to Available Now once that Sunday arrives. Rebuild to update it.

`_src/build_chh.py` owns shared rendering and shared facts/copy. `_src/sites.json`
selects domain, URL prefix, output format, and the Things to Do link. Standalone
page wrappers live in `_src/templates/`; Edge of Liberty retains its Jekyll layout.
Standalone is generated static HTML with `.nojekyll`. Its `.chh-generated.json`
records owned deployment files; only previously owned files can be removed by sync.
Redundant standalone `.txt` sources are not read or staged by the build.

## Secondary commands

```bash
./_src/build.sh build-only       # Both sites; no Git staging, commits, or pushes
./_src/build.sh chh-build        # Standalone only; no Git mutations
./_src/build.sh eol              # Build and publish Edge of Liberty only
./_src/build.sh chh-site         # Build and publish standalone only
./_src/build.sh staging-preview  # Read-only list of included/excluded changed files
```

Existing `vendors`, `dates`, `home`, `chh`, and `permits` commands remain build-only.
`chh` generates the Edge of Liberty `/chh/` pages. Permit generation retains the
existing pypdf/reportlab dependency installation fallback. Permit PDFs stay ignored.

## Publishing selection

No blanket `git add .` is used. Edge of Liberty selection includes:

- Explicit build scripts, settings, templates, and tests.
- Existing tracked site configuration, README, data, includes, and layouts.
- Website HTML/media/styles in existing website directories; recognized description,
  availability, and kitchen inventory files; and new page directories containing
  both `description.txt` and `index.html`.
- Public image/style/proof directories and existing permit-template assets.

Hidden editor folders, workspace files, temporary/local directories, backups,
permit outputs, arbitrary root files, and unknown scripts/data files are excluded.
New types of tooling or data sources should be explicitly added to the selection
policy in `_src/site_build.py`. Review `staging-preview` when adding a new kind of file.
The rules identify website paths and types; they cannot infer intent from file contents.

Standalone selection is limited to its generated manifest and owned outputs, plus
deletions of the 15 explicitly listed obsolete CHH source files during conversion.
Unrelated pre-staged changes in either repository are excluded from site commits
and left staged. Source changes already staged in selected website paths are committed
with their current working-tree contents, as in the previous publishing workflow.

## Local verification

```bash
python3 -m unittest discover -s _src -p test_site_build.py -v
./_src/build.sh build-only
```

Tests mock all publishing calls: they never commit or push. Standalone builds check
local links/assets, canonical URLs, and unresolved templates before syncing output.
Edge of Liberty still uses Jekyll for final layout rendering; for local previews use
`bundle exec jekyll build` with the Ruby/Bundler installation matching Gemfile.lock.
