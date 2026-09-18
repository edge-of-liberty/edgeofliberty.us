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

## Google Sheets Phase 1 — live build input

**Normal CSV-dependent builds retrieve one fresh Planning snapshot from Google
Sheets.** The initial live/manual comparison matched all cells and parser output.
No Sheets writes or order processing are implemented.

The live Planning tab calculates values from DOWNLOAD orders. Fetch retrieves its
formatted results, not formula expressions, from row 1 onward. The sheet remains
the master. The two numeric tab IDs are stored in local configuration; only Planning
is read. The `zzCOMPANY NAME` template row is retained in CSV and excluded by the
existing parser. Future order processing must use API formula-copy operations,
not this flattened CSV export.

### Local environment

```bash
python3 -m venv .venv-sheets
.venv-sheets/bin/python -m pip install -r _src/requirements-sheets.txt
```

This environment is separate from the existing build Python. The Google libraries
are needed only by acquisition/authentication. No dependency installation occurs
inside a publish operation. Tests can run with either Python; auth-specific tests
require the Google libraries.

### One-time Google Cloud setup

1. Sign into Google Cloud Console as `admin@batshitcrazyfarms.com`.
2. Create/select a project under the `batshitcrazyfarms.com` organization. Suggested
   project name: `Edge of Liberty Local Tools`. Organization placement matters:
   signing in with a Workspace account alone does not make an app Internal.
3. In **APIs & Services → Library**, enable **Google Sheets API**.
4. In **Google Auth Platform → Branding**, configure the app and your support/contact
   email. In **Audience**, select **Internal**. If Internal or the organization is
   unavailable, resolve that before continuing; do not silently use External/Testing.
5. In **Data Access**, add only
   `https://www.googleapis.com/auth/spreadsheets.readonly`.
6. In **Clients**, create an OAuth client of type **Desktop app**, then download its
   JSON. Save it outside the repository at:
   `~/.config/edgeofliberty/google/credentials.json`.

Do not paste credential JSON or token contents into chat. No service account,
Drive API, Gmail API, or domain-wide delegation is required. Internal authorization
avoids External/Testing's seven-day refresh-token lifetime; revocation and account
policies can still require reauthorization.

Local `~/.config/edgeofliberty/google/sheets.json` contains the spreadsheet ID,
`planning_sheet_id`, `orders_sheet_id`, year, and account hint. The checked-in
`_src/google_sheets.example.json` documents its format. `token.json` is created after
browser authorization, stored with owner-only permissions, and refreshed locally.
The account hint preselects an account; verify the Workspace account in the browser.

### Authorize, retrieve, compare

From the repository root:

```bash
.venv-sheets/bin/python _src/fetch_planning_sheet.py auth
.venv-sheets/bin/python _src/fetch_planning_sheet.py fetch
```

`auth` opens a browser and waits up to three minutes. Choose the Workspace account
and grant read-only access. `fetch` never opens a browser; missing/revoked credentials
produce a setup error instead. It reads one Planning snapshot, validates the row-9
headers and row-6 capacity values, checks consumed columns for spreadsheet errors,
and runs the existing parser before replacing the local candidate snapshot.

The candidate is `_local/google-sheets/planning-api.csv`. The baseline remains:
`_data/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv`.
Comparison runs automatically after fetch. To rerun without Google access:

```bash
.venv-sheets/bin/python _src/fetch_planning_sheet.py compare
```

`_local/google-sheets/comparison.json` contains hashes, counts, differing cell
coordinates (up to 100), and JSON equivalence—not private cell values. Comparison
ignores only serialization and trailing empty padding; internal blanks and whitespace
remain significant. Exit codes: 0 = equivalent parser output, 2 = parser output
differs and needs review, 1 = setup/retrieval/validation error. Raw-cell differences
are still reported even if parser results match. Neither command invokes a site
build, changes the baseline/build.json, commits, or pushes.

If the live sheet changed since the manual export, inspect differences locally or
compare against a separately saved fresh manual export in a subsequent review.
Do not assume discrepancies are API conversion errors. Let visible calculations
settle first; a read request does not force asynchronous calculations to finish.

### Normal build integration

`./_src/build.sh all`, `build-only`, and `eol` retrieve and validate one fresh
snapshot before any CSV-dependent generation. The vendor, date, homepage, and permit
components all parse that same snapshot using the unchanged `parse_csv.py`.
Individual `vendors`, `dates`, `home`, and `permits` commands also fetch once.
`chh`, `chh-build`, `chh-site`, and `staging-preview` do not access Google Sheets.

The orchestrator invokes `.venv-sheets/bin/python` for acquisition, leaving the
existing build Python and downstream generators unchanged. On Apple Silicon,
acquisition is explicitly launched as ARM64 so an Intel/Rosetta shell cannot load
the native Sheets dependencies in the wrong architecture. Each invocation gets
its own CSV under `_local/google-sheets/build-*/`; the temporary directory is removed
on completion or failure. The comparison snapshot/report remain separate. Auth or
retrieval errors stop the operation before generation/publication; there is no stale
fallback and no browser sign-in during a build. Reauthorize with the explicit `auth`
command if required. Existing Git commit/push behavior is unchanged.

The old tracked `_data/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv`
is **not a build dependency anymore**. It remains the baseline for the explicit
`fetch`/`compare` diagnostics and the baseline round-trip regression test. It has
not been removed or overwritten. Those diagnostics may legitimately report differences
as the live sheet evolves; normal builds do not require equivalence with old data.
Deleting it later would require retiring/updating those comparison/test references,
not changes to the website generators.

Credentials/tokens, `_local/`, and `.venv-sheets/` are excluded from Git and the
website staging policy. The existing tracked CSVs remain untouched in this phase;
their historical presence in Git is not changed by adding ignore patterns.
