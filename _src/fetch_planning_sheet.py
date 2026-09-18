#!/usr/bin/env python3
"""Read Planning's calculated values; compare without changing baseline/build files."""
import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

from google_sheets import DEFAULT_CONFIG, SheetsError, get_client, load_config, private_write, read_request

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / '_data/2026 Edge of Liberty Craft Fairs - Craft Fair Planning.csv'
LOCAL = ROOT / '_local/google-sheets'
CANDIDATE = LOCAL / 'planning-api.csv'
REPORT = LOCAL / 'comparison.json'
PUBLIC_HEADERS = ['Company', 'SPONSOR', 'Short Description', 'Website', 'Store',
                  'Facebook', 'Instagram', 'Youtube', 'TikTok', 'Public email', 'Public phone', 'slug']
ERRORS = {'#REF!', '#VALUE!', '#N/A', '#DIV/0!', '#NAME?', '#NUM!', '#ERROR!', '#SPILL!', '#CALC!', '#LOADING!'}
MONTHS = dict(zip(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], range(1,13)))


def column_name(number):
    name = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.reader(stream))


def normalize_rows(rows):
    """Ignore only trailing blank padding, not spaces or internal blank positions."""
    result = []
    for row in rows:
        row = list(row)
        while row and row[-1] == '':
            row.pop()
        result.append(row)
    while result and not result[-1]:
        result.pop()
    return result


def validate_rows(rows, year):
    if len(rows) < 10:
        raise SheetsError('Planning is empty or missing headers/vendor rows. Expected headers on row 9.')
    headers = rows[8]
    required = PUBLIC_HEADERS + [str(year)]
    missing = [name for name in required if name not in headers]
    if missing:
        raise SheetsError('Planning row 9 is missing required columns: ' + ', '.join(missing))
    nonempty = [h for h in headers if h]
    if len(nonempty) != len(set(nonempty)):
        raise SheetsError('Planning row 9 has duplicate nonempty column headers.')
    dates = []
    for index, header in enumerate(headers):
        match = re.fullmatch(r'([A-Za-z]{3})-(\d{1,2})', header.strip())
        if match:
            try:
                date(year, MONTHS[match[1].title()], int(match[2]))
            except (ValueError, KeyError):
                raise SheetsError(f'Invalid fair-date header at {column_name(index+1)}9.') from None
            dates.append(index)
    if not dates:
        raise SheetsError('Planning row 9 has no fair-date columns.')
    def cell(row, i):
        return str(row[i]).strip() if i < len(row) else ''
    for i in dates:
        value = cell(rows[5], i)
        if value and not value.isdigit():
            raise SheetsError(f'Capacity at {column_name(i+1)}6 is not a whole number; check its formula.')
    indexes = {headers.index(name) for name in required} | set(dates)
    company_index = headers.index('Company')
    for row_number, row in enumerate(rows[9:], 10):
        company = cell(row, company_index)
        if not company or company.lower().startswith('zz'):
            continue
        for i in indexes:
            if cell(row, i) in ERRORS:
                raise SheetsError(f'Spreadsheet error at {column_name(i+1)}{row_number}; check the formula before building.')
    return len(headers)


def planning_values(service, config):
    metadata = read_request(service.spreadsheets().get(
        spreadsheetId=config['spreadsheet_id'],
        fields='sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))'))
    matches = [sheet['properties'] for sheet in metadata.get('sheets', [])
               if sheet['properties']['sheetId'] == config['planning_sheet_id']]
    if len(matches) != 1:
        raise SheetsError('Configured Planning tab ID was not found. No other tab will be substituted.')
    sheet = matches[0]
    grid = sheet.get('gridProperties', {})
    if not grid.get('rowCount') or not grid.get('columnCount'):
        raise SheetsError('Planning tab must be a worksheet with a cell grid.')
    title = "'" + sheet['title'].replace("'", "''") + "'"
    area = f"{title}!A1:{column_name(grid['columnCount'])}{grid['rowCount']}"
    response = read_request(service.spreadsheets().values().get(
        spreadsheetId=config['spreadsheet_id'], range=area,
        majorDimension='ROWS', valueRenderOption='FORMATTED_VALUE'))
    rows = response.get('values', [])
    if any(not isinstance(value, str) for row in rows for value in row):
        raise SheetsError('Unexpected non-text formatted cell value from Google; snapshot was not saved.')
    rows = normalize_rows(rows)
    validate_rows(rows, config['year'])
    width = max(map(len, rows))
    return [row + [''] * (width-len(row)) for row in rows]


def parse_snapshot(path, year):
    process = subprocess.run([sys.executable, str(ROOT / '_src/parse_csv.py'), str(path), str(year)],
                             text=True, capture_output=True)
    if process.returncode:
        raise SheetsError('The existing CSV parser rejected a snapshot. No build files have been replaced.')
    try:
        result = json.loads(process.stdout)
        if not result['vendors'] or not result['dates']:
            raise ValueError()
        return result
    except (ValueError, KeyError, TypeError):
        raise SheetsError('The parser returned empty or invalid vendor/date data.') from None


def fetch_snapshot(service, config, output=CANDIDATE):
    output = Path(output).resolve()
    if not output.is_relative_to(LOCAL.resolve()):
        raise SheetsError("Snapshot output must stay inside _local/google-sheets.")
    rows = planning_values(service, config)
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\r\n').writerows(rows)
    # Validate with the unchanged parser before replacing the previous candidate.
    import tempfile
    LOCAL.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='validate-', dir=LOCAL) as temp:
        candidate = Path(temp) / 'planning.csv'
        private_write(candidate, buffer.getvalue())
        parse_snapshot(candidate, config['year'])
    private_write(output, buffer.getvalue())
    return output


def compare_snapshots(baseline, candidate, year):
    a = read_rows(baseline)
    b = read_rows(candidate)
    validate_rows(a, year)
    validate_rows(b, year)
    a, b = normalize_rows(a), normalize_rows(b)
    differences = []
    total = 0
    for i in range(max(len(a), len(b))):
        left = a[i] if i < len(a) else []
        right = b[i] if i < len(b) else []
        for j in range(max(len(left), len(right))):
            if (left[j] if j < len(left) else '') != (right[j] if j < len(right) else ''):
                total += 1
                if len(differences) < 100:
                    differences.append(f'{column_name(j+1)}{i+1}')
    parsed_a, parsed_b = parse_snapshot(baseline, year), parse_snapshot(candidate, year)
    return {
        'compared_at_utc': datetime.now(timezone.utc).isoformat(),
        'baseline_sha256': hashlib.sha256(Path(baseline).read_bytes()).hexdigest(),
        'candidate_sha256': hashlib.sha256(Path(candidate).read_bytes()).hexdigest(),
        'csv_cells_equal': total == 0, 'changed_cell_count': total,
        'first_changed_cells': differences,
        'parser_results_equal': parsed_a == parsed_b,
        'baseline_vendor_count': len(parsed_a['vendors']), 'candidate_vendor_count': len(parsed_b['vendors']),
        'baseline_date_count': len(parsed_a['dates']), 'candidate_date_count': len(parsed_b['dates']),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['auth', 'fetch', 'compare', 'snapshot'])
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--output', type=Path, help='Local output for the build-only snapshot command')
    args = parser.parse_args()
    if args.output is not None and args.command != 'snapshot':
        parser.error('--output is only supported by snapshot')
    try:
        config = load_config(args.config)
        if args.command == 'auth':
            get_client(config, args.config.expanduser().parent, interactive=True)
            print('Read-only authorization saved locally. No spreadsheet data has been changed.')
            return 0
        if args.command == 'snapshot':
            service = get_client(config, args.config.expanduser().parent)
            output = fetch_snapshot(service, config, args.output or CANDIDATE)
            print(json.dumps({'path': str(output), 'year': config['year']}))
            return 0
        if args.command == 'fetch':
            service = get_client(config, args.config.expanduser().parent)
            fetch_snapshot(service, config)
            print(f'Planning snapshot saved: {CANDIDATE}')
        if not CANDIDATE.exists():
            raise SheetsError('No candidate snapshot exists. Run fetch first.')
        report = compare_snapshots(BASELINE, CANDIDATE, config['year'])
        private_write(REPORT, json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        print(f'Local comparison report: {REPORT}')
        print('Manual baseline is unchanged. No build, commit, or push was run.')
        return 0 if report['parser_results_equal'] else 2
    except (SheetsError, OSError) as exc:
        # OSError messages contain filenames, not CSV cell contents or API bodies.
        print(f'[ERROR] {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
