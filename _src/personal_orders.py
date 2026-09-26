"""Separate personal Gmail authorization and read-only order discovery."""
import argparse
from datetime import datetime, timezone
import json
from google_sheets import CONFIG_DIR, get_credentials
from order_email_review import message_ids

SCOPES = ('https://www.googleapis.com/auth/gmail.readonly',)
ACCOUNT = 'nancy.calafati@gmail.com'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['auth', 'discover'])
    args = parser.parse_args()
    creds = get_credentials({'account_hint': ACCOUNT}, interactive=args.command == 'auth',
                            scopes=SCOPES, token_name='token-orders-personal.json',
                            client_name='credentials-personal.json')
    if args.command == 'auth':
        print(f'Personal Gmail authorization saved to {CONFIG_DIR / "token-orders-personal.json"}. No messages read.')
        return
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    gmail = build('gmail', 'v1', http=AuthorizedHttp(creds, http=httplib2.Http(timeout=30)), cache_discovery=False)
    if gmail.users().getProfile(userId='me').execute()['emailAddress'].lower() != ACCOUNT:
        raise RuntimeError('Wrong personal mailbox authorized; stopped before searching.')
    records = []
    for mid in message_ids(gmail):
        item = gmail.users().messages().get(userId='me', id=mid, format='metadata', metadataHeaders=['Subject', 'Date']).execute(num_retries=2)
        headers = {h['name'].lower(): h['value'] for h in item['payload']['headers']}
        records.append({'order_id': headers['subject'].removeprefix('New Order #'),
                        'timestamp_utc': datetime.fromtimestamp(int(item['internalDate'])/1000, timezone.utc).isoformat()})
    # No local mailbox dataset or spreadsheet writes.
    print(json.dumps({'accepted_messages': len(records), 'distinct_orders': len({r['order_id'] for r in records}),
                      'orders': sorted(records, key=lambda r:r['timestamp_utc'])}, indent=2))


if __name__ == '__main__':
    main()
