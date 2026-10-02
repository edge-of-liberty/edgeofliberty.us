# edgeofliberty.us

Website sources and shared build tooling for Edge of Liberty and Create Happiness House.

## Create Happiness House source of truth

**Make persistent CHH content/code changes in this repository
(`/Users/nancy/edgeofliberty.us/`). Do not hand-edit generated CHH HTML.**
Both this repository's `/chh/` HTML and the standalone
`createhappinesshouse.com` HTML are generated output; builds replace them.

Editable content lives in `chh/description.txt`, `chh/rental-terms/description.txt`,
and the `description.txt` files under `chh/{blue,green,purple,teal}/` and
`chh/{common-upper,common-lower,common-other,travel-nurse-friendly}/`.
Room availability (`rentedUntil.txt`), kitchen inventory (`kitchenStock.txt`),
and photos also live under `chh/`. `_src/build_chh.py` owns shared rendering,
facts/copy, pricing presentation, and structured data. Site settings and wrappers
live in `_src/sites.json` and `_src/templates/`.

## Normal publishing workflow

From this repository, run:

```bash
./_src/process_orders.sh && ./_src/build.sh all
```

`&&` prevents the production build from running if order processing fails.
`build.sh all` regenerates and synchronizes both sites, then performs the normal
commit/push workflow.

This builds the existing Edge of Liberty content (including local permit packets),
its `/chh/` pages, and the standalone CHH site, then commits and pushes website
changes in each repository independently. An unchanged repository is successful;
pending commits are still pushed. If one publication fails, the other is attempted
and the command exits with an error identifying the failed site. Run again to retry.
All builds finish before publishing begins. The two remote pushes are not atomic.

The standalone checkout defaults to `../createhappinesshouse.com`. Override with
`CHH_REPO=/path/to/createhappinesshouse.com` or `--chh-repo /path/to/createhappinesshouse.com`.
Git commands always address the selected repository explicitly.

## Remote vendor call-offs

Command: **`Vendor absent: <vendor>, <date>`**, for example
`Vendor absent: Bright Beads, Oct 4`. Nancy's instruction is authoritative;
do not search for the original email, text, or other communication. This command
authorizes the one-cell override and the normal production rebuild/publish below.
Ask a short clarification for ambiguous vendors or dates; never guess.

Run on Nancy's Mac in `/Users/nancy/edgeofliberty.us`, using existing local Sheets
authorization and the configured 2026 Planning tab:

```bash
.venv-sheets/bin/python -B _src/vendor_absent.py --vendor "Bright Beads" --date "Oct 4"
```

Pass the actual vendor/date as safely quoted arguments. The helper checks both
production repositories are clean/current with remote before changing the sheet;
the existing untracked `BCF.code-workspace` is ignored and must remain untouched.
Resolve blockers without stashing, reverting, pulling, or publishing unrelated work.
Do not change the year gate or any vendor's year value to bypass an exclusion.

**The target attendance formula is intentionally replaced.** Read and record its
underlying value/formula, then write literal `Absent` to that one vendor/date cell.
A formula displaying Absent is not already a literal override. An existing literal
`Absent` is idempotent success; continue to production verification. The helper
stores a private local audit under `_local/vendor-absent/`, outside publication.

Do not modify DOWNLOAD orders, payment/fulfillment status, order history, Type,
year, metadata, other dates, or other cells as part of the override. There is no
refund. Other formulas must remain untouched. The separate normal order-processing
step below retains its existing behavior; it does not implement a call-off refund.

After verifying the live underlying value is literal `Absent`, the helper runs:

```bash
./_src/process_orders.sh && ./_src/build.sh all
```

It checks both repositories against remote main, generated date data, the generated
event page, and the live vendor entry's existing `vendor-absent` / “unable to attend”
display. Live deployment is checked with bounded retries. A successful push alone
is not proof of live publication. If any later step fails, retain Absent and report
the failed step; never restore the formula or retry the spreadsheet write blindly.

The phone response should be only:

```text
✓ Bright Beads — Oct 4 marked Absent
✓ Site rebuilt and published
```

On partial success, retain the first line and replace the second with a short
failure/pending-verification explanation. Do not claim publication before verification.
The helper logs production output for diagnostics; summarize it rather than pasting
it into the phone response. Offline tests use mocks and never call live services:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-sheets/bin/python -B -m unittest discover -s _src -p test_vendor_absent.py -v
```

## Remote order processing and production refresh

Command: **`Process new order`**. Nancy need not provide an order number or email.
**Order processing is best-effort; site refresh is mandatory.** Run on this Mac:

```bash
cd /Users/nancy/edgeofliberty.us
.venv-sheets/bin/python -B _src/process_new_order.py
```

The wrapper checks both production repositories are clean/current with remote,
leaving `BCF.code-workspace` untouched. It runs `./_src/process_orders.sh` once with
its private result file under `_local/process-new-order/`, then independently runs
`./_src/build.sh all`. Zero imports, unsafe notifications, missing vendor setup,
and failed/uncertain importer results do not skip the site refresh. Repository
safety failures or the build/publish itself may block it.

Use only the existing importer's matching, validation, deduplication and write
behavior. Do not interpret unfamiliar emails, repair orders, change matching rules,
create vendors, guess contents, retry uncertain writes, or undo successful imports.
The existing importer rejects an unsafe pending batch before writing; do not add an
alternate partial-batch importer. Report that manual review is required, then build
from current Planning data. If an order was imported but its vendor needs setup,
report the order IDs written to DOWNLOAD orders and the remaining setup requirement,
then still attempt the build. Existing build validation may reject invalid sheet
state; report that build failure without repairing data.

The result receipt distinguishes no write attempted from uncertain writes and
verified imports. Never claim nothing changed after an uncertain write. Report
order and site outcomes separately. An order warning must not be presented as a
website failure if the refresh succeeds, or suppress a real build failure.

Verification checks both repositories against remote main, the live standalone
CHH homepage, Edge homepage date/vendor lists, generated versus live event content,
and the next-fair redirect, with bounded deployment retries. This includes refreshing
date-dependent content when no orders are imported. Existing attendance overrides
remain authoritative; payment does not imply attending.

Keep phone replies to two short lines, for example:

```text
✓ No new orders
✓ Site refreshed and published using current Planning data
```

```text
⚠ Order processing requires manual review — no orders written by this run
✓ Site refreshed and published using current Planning data
```

For verified imports, identify the order IDs; include vendor names only when
verified, not inferred from customer names or free-text instructions. For imported
orders needing setup or uncertain writes, say so accurately on the first line.
If publication fails, use the second line for that failure. Diagnostic output stays
out of the phone summary. Tests mock services and production processes; never use
real orders or production builds as implementation tests.

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

## Known architecture issue — address before 2027 reservations open

Vendor identity and year-specific participation must become separate concepts.
The `2026` field should mean participation in 2026, not whether a vendor exists
in the parsed dataset. A vendor may participate in 2026, 2027, both, or neither.

Currently, `_src/parse_csv.py` excludes rows whose selected-year field is blank
or `0` before creating either vendor or per-date records. `_src/build_vendors.py`
relies on that upstream eligibility gate: its vendor-page and directory/dropdown/
homepage-list generation has no independent year-specific publication filtering.
`_src/build_home.py` embeds the generated vendor list without further filtering.
Simply removing the parser gate would therefore broaden publication.

Before opening 2027 reservations, design support for overlapping years: ingest
2027 reservations/vendors while retaining existing 2026 vendors and event/history
content. Do not require deleting or deactivating 2026 vendors to open the next
season, or lose historical vendor/event information when a vendor does not
participate in the newest season. Define year-specific publication rules for each
consumer separately from general vendor identity and participation data.

**This is a deferred redesign, not authorization to remove the current year gate.**
Keep current behavior until that coordinated change is approved. The immediate
2026 sponsor issue was resolved in the sheet by explicitly setting the three
current Sponsor rows' `2026` fields to `1`.

## Google Sheets Phase 1 — live build input

**Normal CSV-dependent builds retrieve one fresh Planning snapshot from Google
Sheets.** The initial live/manual comparison matched all cells and parser output.
`_src/process_orders.sh` imports Gmail orders into DOWNLOAD orders through the
Sheets API before the build; the Planning snapshot fetch itself is read-only.

The live Planning tab calculates values from DOWNLOAD orders. Fetch retrieves its
formatted results, not formula expressions, from row 1 onward. The sheet remains
the master. The two numeric tab IDs are stored in local configuration; the build
snapshot reads Planning. The `zzCOMPANY NAME` template row is retained in CSV and excluded by the
existing parser. Order processing uses the Sheets API to preserve formulas,
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
