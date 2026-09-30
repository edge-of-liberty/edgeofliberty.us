"""Offline tests; rendering uses temporary directories, never production sites."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fetch_planning_sheet as fetch
import google_sheets as google
import site_build


def fixture():
    rows = [[] for _ in range(8)]
    headers = fetch.PUBLIC_HEADERS + ['2026', 'Sep-20', 'order email']
    rows.append(headers)
    rows[5] = [''] * len(headers)
    rows[5][headers.index('Sep-20')] = '12'
    values = {'Company': 'Example Company', 'slug': 'example-company', '2026': '1',
              'Type': '', 'Sep-20': 'Paid', 'Short Description': 'Art, "gifts"\nand café supplies',
              'Public phone': '0123456789', 'order email': 'private@example.invalid'}
    rows.append([values.get(h, '') for h in headers])
    hidden = {'Company': 'zzCOMPANY NAME', '2026': '1', 'Type': 'Sponsor', 'Sep-20': 'Paid'}
    rows.append([hidden.get(h, '') for h in headers])
    return rows


def write_csv(path, rows, **kwargs):
    with path.open('w', encoding='utf-8', newline='') as stream:
        csv.writer(stream, **kwargs).writerows(rows)


def fake_service(rows, sheet_id=1777984672, title="Planning's Sheet"):
    service = MagicMock()
    service.spreadsheets().get().execute.return_value = {'sheets': [{'properties': {
        'sheetId': sheet_id, 'title': title, 'gridProperties': {'rowCount': 1000, 'columnCount': 43}}}]}
    service.spreadsheets().values().get().execute.return_value = {'values': rows}
    return service


CONFIG = {'spreadsheet_id': 'test', 'planning_sheet_id': 1777984672,
          'orders_sheet_id': 1345923496, 'year': 2026}


class AcquisitionTests(unittest.TestCase):
    def test_values_request_and_padding(self):
        service = fake_service(fixture())
        rows = fetch.planning_values(service, CONFIG)
        kwargs = service.spreadsheets().values().get.call_args.kwargs
        self.assertEqual(kwargs['range'], "'Planning''s Sheet'!A1:AQ1000")
        self.assertEqual(kwargs['valueRenderOption'], 'FORMATTED_VALUE')
        self.assertEqual(kwargs['majorDimension'], 'ROWS')
        self.assertEqual(len(set(map(len, rows))), 1)
        self.assertEqual(rows[0], [''] * len(rows[8]))
        self.assertEqual(rows[8], fixture()[8])
        self.assertNotIn('update', [call[0] for call in service.mock_calls])

    def test_wrong_tab_does_not_read_values(self):
        service = fake_service(fixture(), sheet_id=99)
        service.reset_mock()
        with self.assertRaises(google.SheetsError):
            fetch.planning_values(service, CONFIG)
        service.spreadsheets().values.assert_not_called()

    def test_schema_and_formula_errors(self):
        mutations = [lambda r: r.__setitem__(8, []),
                     lambda r: r[5].__setitem__(r[8].index('Sep-20'), '#REF!'),
                     lambda r: r[9].__setitem__(r[8].index('Sep-20'), '#N/A')]
        for mutate in mutations:
            rows = fixture()
            mutate(rows)
            with self.assertRaises(google.SheetsError):
                fetch.validate_rows(rows, 2026)

    def test_csv_roundtrip_and_parser_equivalence(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/'manual.csv', Path(temp)/'api.csv'
            rows = fixture()
            write_csv(a, rows, lineterminator='\n')
            write_csv(b, [r + [''] * 3 for r in rows] + [[], []], lineterminator='\r\n')
            report = fetch.compare_snapshots(a, b, 2026)
            self.assertTrue(report['csv_cells_equal'])
            self.assertTrue(report['parser_results_equal'])
            vendor = fetch.parse_snapshot(b, 2026)['vendors'][0]
            self.assertEqual(vendor['public_phone'], '0123456789')
            self.assertEqual(vendor['short_description'], 'Art, "gifts"\nand café supplies')
            self.assertNotIn('private@example.invalid', json.dumps(vendor))

    def test_comparison_does_not_log_private_values(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/'manual.csv', Path(temp)/'api.csv'
            rows = fixture()
            write_csv(a, rows)
            rows[9][-1] = 'different-private@example.invalid'
            write_csv(b, rows)
            report = fetch.compare_snapshots(a, b, 2026)
            self.assertFalse(report['csv_cells_equal'])
            self.assertTrue(report['parser_results_equal'])
            self.assertEqual(report['changed_cell_count'], 1)
            self.assertNotIn('private', json.dumps(report))
            rows[9][rows[8].index('Sep-20')] = 'Absent'
            write_csv(b, rows)
            self.assertFalse(fetch.compare_snapshots(a, b, 2026)['parser_results_equal'])

    def test_invalid_fetch_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp)
            candidate = local/'candidate.csv'
            candidate.write_text('previous snapshot')
            with patch.object(fetch, 'LOCAL', local), patch.object(fetch, 'CANDIDATE', candidate):
                with self.assertRaises(google.SheetsError):
                    fetch.fetch_snapshot(fake_service([]), CONFIG, candidate)
            self.assertEqual(candidate.read_text(), 'previous snapshot')

    def test_valid_fetch_writes_private_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp)
            candidate = local/'candidate.csv'
            with patch.object(fetch, 'LOCAL', local), patch.object(fetch, 'CANDIDATE', candidate):
                fetch.fetch_snapshot(fake_service(fixture()), CONFIG, candidate)
            self.assertEqual(candidate.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(fetch.parse_snapshot(candidate, 2026)['vendors']), 1)

    def test_api_errors_do_not_expose_response(self):
        request = MagicMock()
        request.execute.side_effect = RuntimeError('private data and secret token')
        with self.assertRaises(google.SheetsError) as exc:
            google.read_request(request)
        self.assertNotIn('secret', str(exc.exception))
        self.assertNotIn('private data', str(exc.exception))

    def test_real_baseline_parser_stays_equivalent(self):
        before = hashlib.sha256(fetch.BASELINE.read_bytes()).hexdigest()
        rows = fetch.read_rows(fetch.BASELINE)
        # Historical SPONSOR values have no Type meaning. Adapt only this test copy.
        column = rows[8].index('SPONSOR')
        rows[8][column] = 'Type'
        for row in rows[9:]:
            if len(row) > column:
                row[column] = ''
        with tempfile.TemporaryDirectory() as temp:
            adapted, copy = Path(temp) / 'adapted.csv', Path(temp) / 'roundtrip.csv'
            write_csv(adapted, rows)
            parsed = fetch.parse_snapshot(adapted, 2026)
            write_csv(copy, fetch.read_rows(adapted))
            self.assertEqual(parsed, fetch.parse_snapshot(copy, 2026))
            self.assertTrue(all(v['type'] == '' for v in parsed['vendors']))
        self.assertEqual(before, hashlib.sha256(fetch.BASELINE.read_bytes()).hexdigest())

    def test_type_header_is_required_without_legacy_fallback(self):
        rows = fixture()
        rows[8][rows[8].index('Type')] = 'SPONSOR'
        with self.assertRaisesRegex(google.SheetsError, 'Type'):
            fetch.validate_rows(rows, 2026)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'legacy.csv'
            write_csv(path, rows)
            result = subprocess.run([sys.executable, str(fetch.ROOT / '_src/parse_csv.py'),
                                     str(path), '2026'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Type', result.stderr)

    def test_type_classification_rendering_and_order(self):
        rows = fixture()
        headers = rows[8]
        rows = rows[:9]
        entries = [('Zulu Vendor', ''), ('Zulu Sponsor', 'Sponsor'),
                   ('Alpha Truck', 'Food Truck'), ('Alpha Sponsor', 'Sponsor'),
                   ('Legacy Free', 'FREE'), ('Legacy Paid', 'Paid'),
                   ('Other Vendor', 'Other'), ('Lowercase Vendor', 'sponsor'),
                   ('zzCOMPANY NAME', 'Sponsor')]
        for name, kind in entries:
            values = {'Company': name, '2026': '1', 'Type': kind, 'Sep-20': 'Paid'}
            rows.append([values.get(h, '') for h in headers])
        fetch.validate_rows(rows, 2026)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / 'planning.csv'
            write_csv(csv_path, rows)
            parsed = fetch.parse_snapshot(csv_path, 2026)
            self.assertEqual([(v['name'], v['type']) for v in parsed['vendors']], entries[:-1])
            self.assertTrue(all('sponsor' not in v for v in parsed['vendors']))
            self.assertNotIn('zzCOMPANY NAME', json.dumps(parsed))
            data = root / 'build.json'
            data.write_text(json.dumps(parsed))
            subprocess.run([sys.executable, str(fetch.ROOT / '_src/build_vendors.py'),
                            str(root), str(data)], check=True, capture_output=True, text=True)
            sponsors = (root / 'sponsors.html').read_text()
            self.assertLess(sponsors.index('Zulu Sponsor'), sponsors.index('Alpha Sponsor'))
            normal = [v for v in parsed['vendors'] if v['type'] != 'Sponsor']
            for vendor in parsed['vendors']:
                self.assertEqual((root / vendor['slug'] / 'index.html').exists(),
                                 vendor['type'] != 'Sponsor')
            for vendor in normal:
                self.assertNotIn(vendor['name'], sponsors)
            for filename in ['vendors_dropdown.html', 'home_vendors.html']:
                rendered = (root / '_includes' / filename).read_text()
                positions = [rendered.index(v['name']) for v in sorted(normal, key=lambda v: v['name'].lower())]
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn('Zulu Sponsor', rendered)
                self.assertNotIn('Alpha Sponsor', rendered)
                self.assertNotIn('zzCOMPANY NAME', rendered)

    def test_local_files_excluded_from_publish_selection(self):
        for name in ['_local/google-sheets/planning-api.csv', '.venv-sheets/bin/python',
                     'credentials.json', 'token.json', 'sheets.local.json']:
            self.assertFalse(site_build.eol_allowed(name, set()))
        self.assertTrue(site_build.eol_allowed('_src/google_sheets.py', set()))


class BuildIntegrationTests(unittest.TestCase):
    def test_full_build_fetches_once_and_shares_snapshot(self):
        acquisitions = []
        @contextmanager
        def snapshot():
            acquisitions.append(True)
            yield Path('/local/fresh.csv'), '2026'
        with patch.object(site_build, 'planning_snapshot', snapshot), patch.object(site_build, 'build_component') as component, patch.object(site_build, 'tracked', return_value=set()), patch.object(site_build, 'write_sitemap'):
            site_build.build_eol('2026-09-18')
        self.assertEqual(len(acquisitions), 1)
        self.assertEqual([c.args[0] for c in component.call_args_list], ['vendors', 'dates', 'home', 'chh', 'permits'])
        self.assertTrue(all(c.args[2:] == (Path('/local/fresh.csv'), '2026') for c in component.call_args_list))

    def test_retrieval_failure_prevents_generation_and_publication(self):
        with patch.object(sys, 'argv', ['site_build.py', 'all']), patch.object(site_build, 'check_destination'), patch.object(site_build, 'planning_snapshot', side_effect=RuntimeError('Authentication unavailable')), patch.object(site_build, 'build_component') as component, patch.object(site_build, 'build_standalone') as standalone, patch.object(site_build, 'publish') as publish:
            with self.assertRaises(RuntimeError):
                site_build.main()
        component.assert_not_called()
        standalone.assert_not_called()
        publish.assert_not_called()

    def test_chh_commands_do_not_fetch(self):
        for command in ['chh', 'chh-build', 'chh-site']:
            with patch.object(sys, 'argv', ['site_build.py', command]), patch.object(site_build, 'planning_snapshot') as acquire, patch.object(site_build, 'run'), patch.object(site_build, 'check_destination'), patch.object(site_build, 'build_standalone'), patch.object(site_build, 'publish'):
                site_build.main()
            acquire.assert_not_called()

    def test_component_fetches_once_and_passes_csv_to_existing_parser(self):
        for name in ['vendors', 'dates', 'home', 'permits']:
            manager = MagicMock()
            manager.__enter__.return_value = (Path('/local/fresh.csv'), '2026')
            with patch.object(site_build, 'planning_snapshot', return_value=manager) as acquire, patch.object(site_build, 'run', return_value=SimpleNamespace(stdout='{}')) as run, patch.object(Path, 'write_text'), patch.object(site_build.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                site_build.build_component(name, '2026-09-18')
            acquire.assert_called_once()
            self.assertEqual(run.call_args_list[0].args[1:], (site_build.SRC/'parse_csv.py', Path('/local/fresh.csv'), '2026'))

    def test_build_snapshot_failure_does_not_reuse_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python = root/'.venv-sheets/bin/python'
            python.parent.mkdir(parents=True)
            python.touch()
            local = root/'_local/google-sheets'
            local.mkdir(parents=True)
            old = local/'planning-api.csv'
            old.write_text('stale')
            with patch.object(site_build, 'ROOT', root), patch.object(site_build, 'run', side_effect=subprocess.CalledProcessError(1, 'fetch')):
                with self.assertRaises(subprocess.CalledProcessError):
                    with site_build.planning_snapshot():
                        self.fail('Failed acquisition yielded a snapshot')
            self.assertEqual(old.read_text(), 'stale')
            self.assertEqual(list(local.glob('build-*')), [])

    def test_snapshot_command_does_not_consult_baseline(self):
        with patch.object(sys, 'argv', ['fetch_planning_sheet.py', 'snapshot']), patch.object(fetch, 'load_config', return_value=CONFIG), patch.object(fetch, 'get_client'), patch.object(fetch, 'fetch_snapshot', return_value=Path('/local/fresh.csv')), patch.object(fetch, 'compare_snapshots') as compare:
            self.assertEqual(fetch.main(), 0)
        compare.assert_not_called()


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import google_auth_oauthlib.flow
        except ImportError:
            raise unittest.SkipTest('Run with .venv-sheets/bin/python for OAuth tests')

    def test_missing_authorization_never_opens_browser(self):
        with tempfile.TemporaryDirectory() as temp, patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config') as flow:
            with self.assertRaises(google.SheetsError):
                google.get_client(CONFIG, Path(temp))
            flow.assert_not_called()

    def test_missing_desktop_client_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(google.SheetsError, 'Desktop OAuth client'):
                google.get_client(CONFIG, Path(temp), interactive=True)

    def test_broader_saved_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path/'token.json').write_text(json.dumps({'scopes': ['https://www.googleapis.com/auth/spreadsheets']}))
            with self.assertRaisesRegex(google.SheetsError, 'scopes differ'):
                google.get_client(CONFIG, path)

    def test_authorization_uses_readonly_pkce_and_private_token(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path/'credentials.json').write_text('{"installed": {"client_id": "test"}}')
            creds = MagicMock()
            creds.valid = True
            creds.refresh_token = 'test-refresh'
            creds.to_json.return_value = json.dumps({'scopes': list(google.READONLY_SCOPES)})
            flow = MagicMock()
            flow.run_local_server.return_value = creds
            with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config', return_value=flow) as factory, patch('googleapiclient.discovery.build'), patch('google_auth_httplib2.AuthorizedHttp'):
                google.get_client(CONFIG, path, interactive=True)
            self.assertEqual(factory.call_args.kwargs['scopes'], google.READONLY_SCOPES)
            self.assertTrue(factory.call_args.kwargs['autogenerate_code_verifier'])
            self.assertEqual(flow.run_local_server.call_args.kwargs['host'], '127.0.0.1')
            self.assertEqual((path/'token.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual((path/'credentials.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
