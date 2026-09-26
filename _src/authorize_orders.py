"""Explicit order-tool OAuth only: no Gmail or Sheets service/data calls."""
import argparse
import sys

from google_sheets import CONFIG_DIR, SheetsError, get_credentials

ORDER_SCOPES = (
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        get_credentials(
            {'account_hint': 'admin@batshitcrazyfarms.com'},
            interactive=True, scopes=ORDER_SCOPES, token_name='token-orders.json',
        )
    except SheetsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Order-tool authorization saved: {CONFIG_DIR / "token-orders.json"}')
    print('No Gmail messages or spreadsheet data accessed. Website token unchanged.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
