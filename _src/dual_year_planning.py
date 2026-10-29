"""Website-only 2026/2027 Planning snapshots; operational configuration stays unchanged."""
import csv
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import re
import subprocess
import sys

from google_sheets import SheetsError
from fetch_planning_sheet import planning_values, column_name

SOURCES = ((2026, 1777984672, 'Craft Fair Planning'),
           (2027, 514124464, '2027 Craft Fair Planning'))
ROOT = Path(__file__).resolve().parent.parent


def validate_date_cells(headers, cells, year, title):
    for i, header in enumerate(headers):
        match = re.fullmatch(r'([A-Za-z]{3})-(\d{1,2})', header.strip())
        if not match:
            continue
        cell = cells[i] if i < len(cells) else {}
        serial = cell.get('effectiveValue', {}).get('numberValue')
        try:
            actual = (datetime(1899, 12, 30) + timedelta(days=serial)).date()
            expected = datetime.strptime(f'{header}-{year}', '%b-%d-%Y').date()
            assert cell.get('effectiveFormat', {}).get('numberFormat', {}).get('type') == 'DATE'
            assert actual == expected
        except (TypeError, ValueError, OverflowError, AssertionError):
            raise SheetsError(f'{title}!{column_name(i+1)}9: underlying date must be {header}-{year}; got {serial!r}') from None


def merge(seasons):
    vendors = {}; dates = {}
    for year, data in seasons:
        seen = set()
        for v in data['vendors']:
            slug = v['slug']
            if not slug or slug in seen:
                raise SheetsError(f'{year}: duplicate or missing vendor slug: {slug!r}')
            seen.add(slug)
            if slug not in vendors:
                vendors[slug] = dict(v, dates=list(v['dates']), participation=dict(v['participation']))
                continue
            old = vendors[slug]
            if old['name'] != v['name']:
                raise SheetsError(f'Ambiguous vendor identity {slug}: {old["name"]!r} versus {v["name"]!r}')
            if old['type'] != v['type']:
                raise SheetsError(f'Type conflict for {v["name"]} ({slug}): {old["type"]!r} versus {v["type"]!r}')
            # Established 2026 public metadata wins; fill only missing fields.
            for key, value in v.items():
                if key not in ('dates', 'participation') and not old.get(key):
                    old[key] = value
            old['participation'].update(v['participation'])
            old['dates'].extend(v['dates'])
        overlap = set(dates) & set(data['dates'])
        if overlap:
            raise SheetsError(f'Duplicate event dates: {sorted(overlap)}')
        dates.update(data['dates'])
    return {'vendors': list(vendors.values()), 'dates': dates, 'years': [2027, 2026]}


def fetch_website(service, config):
    tabs = service.spreadsheets().get(spreadsheetId=config['spreadsheet_id'],
        fields='sheets(properties)').execute(num_retries=2)['sheets']
    seasons = []
    for year, sid, title in SOURCES:
        matches = [t['properties'] for t in tabs if t['properties']['sheetId'] == sid]
        if len(matches) != 1 or matches[0]['title'] != title:
            raise SheetsError(f'Expected Planning tab {title!r}, sheet ID {sid}')
        rows = planning_values(service, dict(config, planning_sheet_id=sid, year=year))
        # Unlike formatted CSV, native date cells retain the real year.
        native = service.spreadsheets().get(spreadsheetId=config['spreadsheet_id'],
            ranges=[f"'{title}'!A9:{column_name(len(rows[8]))}9"],
            fields='sheets(data(rowData(values(effectiveValue,effectiveFormat(numberFormat)))))').execute(num_retries=2)
        cells = native['sheets'][0]['data'][0]['rowData'][0].get('values', [])
        validate_date_cells(rows[8], cells, year, title)
        # Explicit existing slugs are the cross-tab identity, never row numbers/names.
        headers = rows[8]; ni = headers.index('Company'); si = headers.index('slug')
        for rn, row in enumerate(rows[9:], 10):
            name = row[ni].strip()
            if name and not name.lower().startswith('zz') and not row[si].strip():
                raise SheetsError(f'{title}!{column_name(si+1)}{rn}: missing identity slug')
        buffer = io.StringIO(); csv.writer(buffer).writerows(rows)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'_src/parse_csv.py'), '/dev/stdin', str(year), '--identities'],
            input=buffer.getvalue(), text=True, capture_output=True)
        if result.returncode:
            raise SheetsError(f'{title}: CSV parsing failed: {result.stderr.strip()}')
        seasons.append((year, json.loads(result.stdout)))
    return merge(seasons)
