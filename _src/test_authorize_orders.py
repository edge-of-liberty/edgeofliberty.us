"""Offline OAuth isolation checks; all consent/network entry points mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import authorize_orders as orders
import google_sheets as google


class OrderAuthorizationTests(unittest.TestCase):
    def test_consent_saves_only_order_token_without_service_clients(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            website = root / 'token.json'
            website.write_text('website-token-sentinel')
            website.chmod(0o640)
            before = website.stat()
            (root / 'credentials.json').write_text('{"installed": {"client_id": "test"}}')
            creds = MagicMock(valid=True, refresh_token='fake-refresh')
            creds.to_json.return_value = json.dumps({'scopes': list(orders.ORDER_SCOPES)})
            flow = MagicMock()
            flow.run_local_server.return_value = creds
            with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config', return_value=flow) as factory, patch('googleapiclient.discovery.build') as build:
                google.get_credentials({}, root, interactive=True,
                                       scopes=orders.ORDER_SCOPES, token_name='token-orders.json')
            self.assertEqual(factory.call_args.kwargs['scopes'], (
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/spreadsheets'))
            self.assertTrue(factory.call_args.kwargs['autogenerate_code_verifier'])
            self.assertEqual(flow.run_local_server.call_args.kwargs['access_type'], 'offline')
            build.assert_not_called()
            self.assertEqual(website.read_text(), 'website-token-sentinel')
            self.assertEqual(website.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertEqual(website.stat().st_mode, before.st_mode)
            self.assertEqual((root / 'token-orders.json').stat().st_mode & 0o777, 0o600)

    def test_missing_order_token_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'token.json').write_text('must not be read')
            with patch('google.oauth2.credentials.Credentials.from_authorized_user_info') as load, patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config') as flow:
                with self.assertRaisesRegex(google.SheetsError, 'not ready'):
                    google.get_credentials({}, root, scopes=orders.ORDER_SCOPES,
                                           token_name='token-orders.json')
            load.assert_not_called()
            flow.assert_not_called()

    def test_command_selects_fixed_account_scopes_and_token(self):
        with patch('sys.argv', ['authorize_orders.py']), patch.object(orders, 'get_credentials') as auth:
            self.assertEqual(orders.main(), 0)
        auth.assert_called_once_with(
            {'account_hint': 'admin@batshitcrazyfarms.com'}, interactive=True,
            scopes=orders.ORDER_SCOPES, token_name='token-orders.json')

    def test_failed_consent_does_not_write_token(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'credentials.json').write_text('{"installed": {}}')
            with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config') as factory:
                factory.return_value.run_local_server.side_effect = RuntimeError('secret')
                with self.assertRaisesRegex(google.SheetsError, 'did not complete'):
                    google.get_credentials({}, root, interactive=True,
                                           scopes=orders.ORDER_SCOPES, token_name='token-orders.json')
            self.assertFalse((root / 'token-orders.json').exists())


if __name__ == '__main__':
    unittest.main()
