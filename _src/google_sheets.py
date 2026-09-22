"""Local OAuth and Google Sheets client; independent of CSV/build/order logic."""
import json
import os
from pathlib import Path
import tempfile

READONLY_SCOPES = ('https://www.googleapis.com/auth/spreadsheets.readonly',)
CONFIG_DIR = Path.home() / '.config/edgeofliberty/google'
DEFAULT_CONFIG = CONFIG_DIR / 'sheets.json'


class SheetsError(RuntimeError):
    """Safe, user-facing message (never includes cell values or token responses)."""


def private_write(path, text):
    """Replace local data atomically, with owner-only file permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_config(path=DEFAULT_CONFIG):
    try:
        config = json.loads(Path(path).expanduser().read_text())
    except (OSError, ValueError):
        raise SheetsError(f'Cannot read configuration: {path}. See the Google Sheets setup in README.md.') from None
    if not isinstance(config, dict):
        raise SheetsError('Sheets configuration must be a JSON object.')
    if not isinstance(config.get('spreadsheet_id'), str) or not config['spreadsheet_id'].strip():
        raise SheetsError('Configuration requires spreadsheet_id.')
    for key in ('planning_sheet_id', 'orders_sheet_id', 'year'):
        if type(config.get(key)) is not int or config[key] < 0:
            raise SheetsError(f'Configuration requires an integer {key}.')
    if not 2000 <= config['year'] <= 2100:
        raise SheetsError('Configuration year must be between 2000 and 2100.')
    return config


def get_credentials(config, auth_dir=CONFIG_DIR, *, interactive=False,
                    scopes=READONLY_SCOPES, token_name="token.json",
                    client_name="credentials.json"):
    """Authorize only on explicit request; normal reads refresh stored tokens.

    Token selection is explicit; a missing token never falls back to another file.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SheetsError(f'Google library import failed ({exc.name}). Use .venv-sheets/bin/python and install _src/requirements-sheets.txt.') from None
    auth_dir = Path(auth_dir).expanduser()
    if Path(client_name).name != client_name or not client_name.startswith('credentials') or not client_name.endswith('.json'):
        raise SheetsError('Invalid OAuth client filename.')
    client_file = auth_dir / client_name
    if Path(token_name).name != token_name or token_name in ('', '.', '..', 'credentials.json'):
        raise SheetsError('Invalid authorization token filename.')
    token_file = auth_dir / token_name
    creds = None
    if token_file.exists() and not interactive:
        try:
            info = json.loads(token_file.read_text())
            if set(info.get('scopes', [])) != set(scopes):
                raise SheetsError('Stored authorization scopes differ. Run the auth command explicitly to authorize the requested access.')
            creds = Credentials.from_authorized_user_info(info, scopes=scopes)
            os.chmod(token_file, 0o600)
            if not creds.valid and creds.refresh_token:
                request = Request()
                creds.refresh(lambda *a, **kw: request(*a, **{**kw, 'timeout': 30}))
                private_write(token_file, creds.to_json())
        except SheetsError:
            raise
        except Exception:
            raise SheetsError('Saved Google authorization could not be refreshed. Run the auth command again; the build has not fetched data.') from None
    if interactive:
        try:
            client_info = json.loads(client_file.read_text())
        except (OSError, ValueError):
            raise SheetsError(f'Download a Desktop OAuth client JSON to {client_file}, then rerun auth.') from None
        if 'installed' not in client_info:
            raise SheetsError('credentials.json must contain a Desktop app OAuth client, not a web client or service account.')
        os.chmod(client_file, 0o600)
        try:
            flow = InstalledAppFlow.from_client_config(client_info, scopes=scopes, autogenerate_code_verifier=True)
            creds = flow.run_local_server(
                host='127.0.0.1', port=0, timeout_seconds=180,
                access_type='offline', prompt='consent',
                login_hint=config.get('account_hint', 'admin@batshitcrazyfarms.com'),
                authorization_prompt_message='Opening Google authorization in your browser. Choose the configured Workspace account.',
                success_message='Authorization received. You may close this tab and return to your terminal.',
            )
            if not creds.refresh_token or not creds.has_scopes(scopes):
                raise SheetsError('Google did not grant the requested offline authorization. Run auth again.')
            private_write(token_file, creds.to_json())
        except SheetsError:
            raise
        except Exception:
            raise SheetsError('Google authorization did not complete. Check the browser consent and Desktop/Internal client setup, then retry auth.') from None
    if not creds or not creds.valid:
        raise SheetsError('Google authorization is not ready. Run the auth command first. No browser is opened by fetch or build commands.')
    return creds


def get_client(config, auth_dir=CONFIG_DIR, *, interactive=False, scopes=READONLY_SCOPES):
    """Existing website Sheets client, using its original token.json."""
    creds = get_credentials(config, auth_dir, interactive=interactive, scopes=scopes)
    try:
        from googleapiclient.discovery import build
        import google_auth_httplib2
        import httplib2
        return build('sheets', 'v4', http=google_auth_httplib2.AuthorizedHttp(
            creds, http=httplib2.Http(timeout=30)), cache_discovery=False)
    except Exception:
        raise SheetsError('Could not initialize the Google Sheets client. Check network access and installed dependencies.') from None


def read_request(request):
    try:
        return request.execute(num_retries=2)
    except Exception as exc:
        status = getattr(getattr(exc, 'resp', None), 'status', None)
        detail = {
            401: 'Authorization expired; run auth again.',
            403: 'Check that Sheets API is enabled and the authorized account has access; Workspace policy may also restrict this app.',
            404: 'Check the spreadsheet ID and the authorized account access.',
            429: 'Google rate limit reached; retry later.',
        }.get(status, 'Check network connectivity and Google service availability, then retry.')
        raise SheetsError(f'Sheets read failed{f" (HTTP {status})" if status else ""}. {detail}') from None
