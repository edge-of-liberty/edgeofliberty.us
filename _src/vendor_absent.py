"""One-cell attendance override followed by the established production workflow."""
import argparse
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import time
import unicodedata
import uuid

from authorize_orders import ORDER_SCOPES
from google_sheets import get_credentials, load_config, private_write

ROOT = Path('/Users/nancy/edgeofliberty.us')
CHH = Path('/Users/nancy/createhappinesshouse.com')
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


class Stop(RuntimeError):
    pass


def normalized(value):
    return ' '.join(value.split()).casefold()


def requested_date(value, year):
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            result = date.fromisoformat(value)
        else:
            match = re.fullmatch(r'([A-Za-z]+)[ -]+(\d{1,2})(?:,?\s+(\d{4}))?', value.strip())
            if not match:
                raise ValueError()
            months = [i for i, name in enumerate(MONTHS, 1)
                      if match[1].lower() in (name.lower(), name[:3].lower())]
            if len(months) != 1:
                raise ValueError()
            result = date(int(match[3] or year), months[0], int(match[2]))
        if result.year != year:
            raise ValueError()
        return result
    except ValueError:
        raise Stop(f'Which fair date in {year}? Use a month and day.') from None


def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value.replace('&', '')).strip('-')


def resolve(rows, vendor, requested, year):
    if len(rows) < 9:
        raise Stop('Planning header row 9 is missing.')
    headers = rows[8]
    for key in ('Company', str(year)):
        if headers.count(key) != 1:
            raise Stop(f'Planning must have exactly one {key} column.')
    day = requested_date(requested, year)
    columns = [i for i, h in enumerate(headers)
               if h.strip().casefold() == f'{MONTHS[day.month-1][:3]}-{day.day}'.casefold()
               or h.strip().casefold() == f'{MONTHS[day.month-1][:3]}-{day.day:02d}'.casefold()]
    if len(columns) != 1:
        raise Stop('Fair date is missing or ambiguous in Planning; please clarify.')
    def cell(row, key):
        i = headers.index(key)
        return str(row[i]).strip() if i < len(row) else ''
    candidates = [(i, row) for i, row in enumerate(rows[9:], 9)
                  if cell(row, 'Company') and not cell(row, 'Company').casefold().startswith('zz')]
    matches = [(i, row) for i, row in candidates if normalized(cell(row, 'Company')) == normalized(vendor)]
    if len(matches) != 1:
        suggestions = [cell(row, 'Company') for _, row in candidates
                       if normalized(vendor) in normalized(cell(row, 'Company'))][:5]
        raise Stop('Which vendor? ' + (', '.join(suggestions) if suggestions else 'Use the exact Planning company name.'))
    i, row = matches[0]
    if cell(row, str(year)) in ('', '0'):
        raise Stop(f'Vendor is excluded by the {year} publication gate; no cells changed.')
    name = cell(row, 'Company')
    slug = slugify(cell(row, 'slug') if 'slug' in headers and cell(row, 'slug') else name)
    if not slug:
        raise Stop('Vendor has no usable page slug.')
    return {'row': i, 'column': columns[0], 'name': name, 'slug': slug,
            'date': day.isoformat(), 'event': f'{MONTHS[day.month-1].lower()}-{day.day:02d}-{year}'}


def service(config):
    # Reuse existing authorization; create only a Sheets client, never read Gmail here.
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    creds = get_credentials(config, scopes=ORDER_SCOPES, token_name='token-orders.json')
    return build('sheets', 'v4', http=AuthorizedHttp(creds, http=httplib2.Http(timeout=30)),
                 cache_discovery=False)


def snapshot(api, config):
    book = config['spreadsheet_id']
    metadata = api.spreadsheets().get(spreadsheetId=book,
        fields='properties(title),sheets(properties)').execute(num_retries=2)
    if metadata['properties']['title'] != '2026 Edge of Liberty Craft Fairs' or config['year'] != 2026:
        raise Stop('Configured workbook/year differs from the approved 2026 workflow.')
    tabs = [s['properties'] for s in metadata['sheets']
            if s['properties']['sheetId'] == config['planning_sheet_id']]
    if len(tabs) != 1 or tabs[0]['title'] != 'Craft Fair Planning':
        raise Stop('Configured Planning tab does not match Craft Fair Planning.')
    rows = api.spreadsheets().values().get(spreadsheetId=book, range="'Craft Fair Planning'",
        valueRenderOption='FORMATTED_VALUE').execute(num_retries=2).get('values', [])
    return rows


def entered(api, config, target):
    area = {'sheetId': config['planning_sheet_id'], 'startRowIndex': target['row'],
            'endRowIndex': target['row']+1, 'startColumnIndex': target['column'],
            'endColumnIndex': target['column']+1}
    result = api.spreadsheets().getByDataFilter(spreadsheetId=config['spreadsheet_id'],
        body={'dataFilters': [{'gridRange': area}], 'includeGridData': True},
        fields='sheets(data(rowData(values(userEnteredValue))))').execute(num_retries=2)
    sheets = result.get('sheets', [])
    if len(sheets) != 1:
        raise Stop('Could not read the target attendance cell.')
    data = sheets[0].get('data', [{}])[0].get('rowData', [{}])[0].get('values', [{}])[0]
    return data.get('userEnteredValue', {})


def override(api, config, vendor, day, audit):
    target = resolve(snapshot(api, config), vendor, day, config['year'])
    before = entered(api, config, target)
    audit({'phase': 'before', 'target': target, 'before': before})
    if resolve(snapshot(api, config), vendor, day, config['year']) != target or entered(api, config, target) != before:
        raise Stop('Planning changed during verification; retry after checking the sheet.')
    if before != {'stringValue': 'Absent'}:
        # Intentionally replace THIS cell's formula/status, never adjacent formulas or orders.
        request = {'updateCells': {
            'range': {'sheetId': config['planning_sheet_id'], 'startRowIndex': target['row'],
                      'endRowIndex': target['row']+1, 'startColumnIndex': target['column'],
                      'endColumnIndex': target['column']+1},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': 'Absent'}}]}],
            'fields': 'userEnteredValue'}}
        try:
            api.spreadsheets().batchUpdate(spreadsheetId=config['spreadsheet_id'],
                body={'requests': [request]}).execute(num_retries=0)
        except Exception:
            # A timeout may have happened after the write. Read back; never blindly retry.
            if entered(api, config, target) != {'stringValue': 'Absent'}:
                raise Stop('Attendance write failed or is uncertain; inspect the cell. No rollback attempted.') from None
    if entered(api, config, target) != {'stringValue': 'Absent'}:
        raise Stop('Attendance readback is not literal Absent; stopped without rollback.')
    if resolve(snapshot(api, config), vendor, day, config['year']) != target:
        raise Stop('Planning identity changed after write; inspect before publishing. No rollback attempted.')
    audit({'phase': 'verified', 'target': target, 'after': {'stringValue': 'Absent'}})
    return target


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def check_repositories():
    for repo in (ROOT, CHH):
        if git(repo, 'branch', '--show-current') != 'main':
            raise Stop(f'{repo.name}: expected main branch.')
        status = git(repo, 'status', '--porcelain', '--untracked-files=all')
        if any(line != '?? BCF.code-workspace' for line in status.splitlines()):
            raise Stop(f'{repo.name}: pending files need review before production publishing.')
        remote = git(repo, 'ls-remote', 'origin', 'refs/heads/main').split()
        if not remote or git(repo, 'rev-parse', 'HEAD') != remote[0]:
            raise Stop(f'{repo.name}: local HEAD differs from remote main; review first.')


class AbsenceEntry(HTMLParser):
    def __init__(self, slug):
        super().__init__(); self.slug = slug; self.active = False; self.link = False; self.text = ''; self.found = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'li':
            self.active = 'vendor-absent' in attrs.get('class', '').split(); self.link = False; self.text = ''
        if self.active and tag == 'a' and attrs.get('href') == f'/{self.slug}/':
            self.link = True
    def handle_data(self, data):
        if self.active: self.text += data
    def handle_endtag(self, tag):
        if tag == 'li':
            self.found |= self.active and self.link and 'unable to attend' in self.text
            self.active = False


def reflects_absence(html, slug):
    parser = AbsenceEntry(slug); parser.feed(html); return parser.found


def verify_output(target):
    data = json.loads((ROOT / '_data/build.json').read_text())
    entries = [v for v in data['dates'][target['event']]['vendors'] if v['slug'] == target['slug']]
    if len(entries) != 1 or entries[0]['status'] != 'Absent':
        raise Stop('Generated date data does not show the intended vendor as Absent.')
    if not reflects_absence((ROOT / target['event'] / 'index.html').read_text(), target['slug']):
        raise Stop('Generated event page does not show the vendor as absent.')
    url = f"https://www.edgeofliberty.us/{target['event']}/"
    for attempt in range(12):
        result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                                 '--max-time', '15', url], capture_output=True, text=True)
        if result.returncode == 0 and reflects_absence(result.stdout, target['slug']): return
        if attempt < 11: time.sleep(10)
    raise Stop('Pushed, but live absence display is not verified yet.')


def run(vendor, day):
    check_repositories()
    config = load_config()
    api = service(config)
    audit_path = ROOT / '_local/vendor-absent' / (uuid.uuid4().hex + '.json')
    records = []
    def audit(record):
        records.append({'time': datetime.now(timezone.utc).isoformat(), **record})
        private_write(audit_path, json.dumps(records, indent=2) + '\n')
    target = override(api, config, vendor, day, audit)
    try:
        subprocess.run(['bash', '-c', './_src/process_orders.sh && ./_src/build.sh all'], cwd=ROOT, check=True)
        check_repositories()
        verify_output(target)
    except Exception as exc:
        audit({'phase': 'production_failed', 'target': target})
        raise Stop(f"{target['name']} — {target['date']} marked Absent; rebuild/publish verification failed. Absent was not undone. {exc}") from None
    audit({'phase': 'published', 'target': target})
    print(f"✓ {target['name']} — {target['date']} marked Absent\n✓ Site rebuilt and published")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True)
    parser.add_argument('--date', required=True)
    args = parser.parse_args()
    try: run(args.vendor, args.date)
    except Stop as exc:
        print(f'⚠ {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
