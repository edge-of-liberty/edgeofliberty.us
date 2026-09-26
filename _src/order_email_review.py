"""One-shot Gmail review export. Never writes production tabs or Gmail messages."""
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import secrets

from authorize_orders import ORDER_SCOPES
from google_sheets import get_credentials, load_config, private_write

TITLE = 'Order Email Review'
QUERY = 'subject:"New Order"'
LOCAL = Path(__file__).resolve().parents[1] / '_local/order-review'
HEADERS = ['Order #', 'Email Address (private)', 'Order Date', 'Payment Status',
           'Customer Name', 'Phone (private)', 'LineItem Name', 'LineItem SKU',
           'LineItem Qty', 'Unit Price', 'Line Total', 'Subtotal', 'Order Total',
           'Special Instructions', 'Payment Method (source)', 'Item Details (source)',
           'Parser / Review Notes', 'Gmail Message ID', 'Gmail Timestamp (UTC)',
           'Email Date Header', 'Email Subject', 'Gmail Link', 'Message Text (source)',
           'Reconciliation Notes (manual)']
MONEY = r'\$([\d,]+\.\d{2})'


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('style', 'script'): self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.extend(x.strip() for x in data.splitlines() if x.strip())


def text_from_mime(raw):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    part = message.get_body(preferencelist=('html', 'plain'))
    if part is None: return message, ''
    body = part.get_content()
    if part.get_content_type() == 'text/html' or '<html' in body.lower():
        parser = TextParser(); parser.feed(body); body = '\n'.join(parser.parts)
    return message, body


def match(pattern, text, flags=0):
    result = re.search(pattern, text, flags)
    return result.group(1).strip() if result else ''


def parse_message(message_id, internal_date, raw):
    notes = []
    try:
        message, text = text_from_mime(raw)
    except Exception:
        message, text = {}, ''
        notes.append('MIME/body decode failed; inspect original Gmail message')
    subject = str(message.get('Subject', ''))
    order = match(r'Order:\s*(\w+)', text) or match(r'New Order\s*#([\w-]+)', subject, re.I)
    date = match(r'Date:\s*(\d{4}-\d{2}-\d{2})', text)
    customer = match(r'New order from:\s*([^\n]+)', text, re.I)
    contact = text.split('VIEW ORDER')[0]
    email = match(r'([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})', contact)
    phone = match(r'^([+()\d][\d ()+.-]{6,})$', contact, re.M)
    payment_method = match(r'Payment Method\s*\n([^\n]+)', text)
    payment = 'Unpaid' if re.search(r'\bpay\s+by\s+cash\b', text, re.I) else 'Paid'
    special = match(r'Special Instructions\s*\n(.*?)(?=\n(?:Order Summary|Payment Method|Pickup Address|Shipping Address)|\Z)', text, re.S)
    subtotal = match(r'Subtotal:\s*' + MONEY, text)
    total = match(r'Order Total:\s*' + MONEY, text)
    for name, value in [('order ID', order), ('order date', date), ('customer email', email), ('customer name', customer)]:
        if not value: notes.append('Missing ' + name)
    try:
        stamp = datetime.fromtimestamp(int(internal_date) / 1000, timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        stamp = ''; notes.append('Missing/invalid Gmail timestamp')
    section = match(r'Order Summary\s*\n(.*?)(?=\nSubtotal:|\Z)', text, re.S)
    lines = section.splitlines()
    items = []; start = 0
    # Each recognized SKU item ends at its displayed total; never split on names.
    for idx, line in enumerate(lines):
        if not re.match(r'^SKU\s*:', line): continue
        sku = line.split(':', 1)[1].strip()
        next_sku = next((j for j in range(idx+1, len(lines)) if lines[j].startswith('SKU:')), len(lines))
        prices = [j for j in range(idx+1, next_sku) if re.fullmatch(MONEY + r'(?:\s*[×x]\s*\d+)?', lines[j])]
        item_notes = []
        qty = ''; unit = ''; line_total = ''; end = idx + 1
        if prices:
            first = prices[0]; unit = match(MONEY, lines[first]).replace(',', '')
            multiplier = match(r'[×x]\s*(\d+)', lines[first])
            qty = multiplier or '1'
            end = first + 1
            if multiplier:
                if len(prices) > 1:
                    line_total = match(MONEY, lines[prices[1]]).replace(',', ''); end = prices[1]+1
                else: item_notes.append('Quantity displayed but line total missing')
            else: line_total = unit
            if line_total and Decimal(unit)*int(qty) != Decimal(line_total):
                item_notes.append('Unit price × quantity differs from line total')
        else: item_notes.append('Item price/quantity not recognized')
        name = '\n'.join(lines[start:idx]).strip()
        if not name: item_notes.append('Item name missing')
        items.append((name, sku, qty, unit, line_total, '\n'.join(lines[start:end]), item_notes))
        start = end
    if not items:
        items = [('', '', '', '', '', section, ['No recognizable SKU line items; inspect source'])]
    elif '\n'.join(lines[start:]).strip():
        notes.append('Unparsed trailing order-summary text; inspect source')
    if subtotal and all(i[4] for i in items):
        if sum(Decimal(i[4]) for i in items) != Decimal(subtotal.replace(',', '')):
            notes.append('Sum of line totals differs from subtotal (check discounts/options)')
    if len(text) > 45000:
        notes.append('Source text truncated to 45000 characters; see Gmail')
    rows = []
    for name, sku, qty, unit, amount, source, item_notes in items:
        rows.append([order, email, date, payment, customer, phone, name, sku, qty,
                     unit, amount, subtotal, total, special, payment_method, source,
                     '; '.join(notes + item_notes), message_id, stamp, str(message.get('Date', '')),
                     subject, 'https://mail.google.com/mail/u/0/#all/' + message_id,
                     text[:45000], ''])
    return rows


def clients(config):
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    creds = get_credentials(config, scopes=ORDER_SCOPES, token_name='token-orders.json')
    return tuple(build(api, version, http=AuthorizedHttp(creds, http=httplib2.Http(timeout=60)),
                       cache_discovery=False) for api, version in [('gmail', 'v1'), ('sheets', 'v4')])


def metadata(sheets, spreadsheet):
    return sheets.spreadsheets().get(spreadsheetId=spreadsheet,
        fields='sheets(properties)').execute(num_retries=2)['sheets']


def ensure_absent(tabs):
    if any(t['properties']['title'] == TITLE for t in tabs):
        raise RuntimeError('Order Email Review already exists; stopped without writing.')


def message_ids(gmail, query=QUERY):
    ids = []; seen = set(); page = None; pages = set()
    while True:
        args = dict(userId='me', q=query, maxResults=500, includeSpamTrash=True)
        if page: args['pageToken'] = page
        result = gmail.users().messages().list(**args).execute(num_retries=2)
        for item in result.get('messages', []):
            if item['id'] in seen: continue
            seen.add(item['id'])
            message = gmail.users().messages().get(
                userId='me', id=item['id'], format='metadata',
                metadataHeaders=['Subject']).execute(num_retries=2)
            subject = next((h['value'] for h in message.get('payload', {}).get('headers', [])
                            if h['name'].lower() == 'subject'), '')
            if re.fullmatch(r'New Order #R\d+', subject): ids.append(item['id'])
        page = result.get('nextPageToken')
        if not page: return ids
        if page in pages: raise RuntimeError('Repeated Gmail pagination token; no sheet written.')
        pages.add(page)


def fetch_rows(gmail, query=QUERY):
    ids = message_ids(gmail, query); rows = []
    for mid in ids:
        result = gmail.users().messages().get(userId='me', id=mid, format='raw').execute(num_retries=2)
        try:
            raw = base64.urlsafe_b64decode(result.get('raw', '') + '===')
            rows.extend(parse_message(mid, result.get('internalDate'), raw))
        except Exception:
            fallback = parse_message(mid, result.get('internalDate'), b'')
            fallback[0][16] += '; Unexpected parse failure; inspect original Gmail message'
            rows.extend(fallback)
    rows.sort(key=lambda r: (r[18], r[17]))
    return ids, rows


def summary(ids, rows):
    unique = {r[17]: r for r in rows}
    def span(index):
        vals = sorted({r[index] for r in rows if r[index]})
        return [vals[0], vals[-1]] if vals else []
    warning_rows = [r for r in rows if r[16]]
    days = sorted({r[18][:10] for r in rows if r[18]})
    gaps = []
    for a, b in zip(days, days[1:]):
        delta = (datetime.fromisoformat(b)-datetime.fromisoformat(a)).days
        if delta > 1: gaps.append({'from': a, 'to': b, 'days_between_messages': delta})
    return dict(messages=len(ids), message_dates_utc=span(18), order_dates=span(2),
                distinct_order_ids=len({r[0] for r in rows if r[0]}), line_item_rows=len(rows),
                payment_messages=dict(Counter(r[3] for r in unique.values())),
                payment_rows=dict(Counter(r[3] for r in rows)),
                warning_messages=len({r[17] for r in warning_rows}),
                warning_order_ids=len({r[0] for r in warning_rows if r[0]}),
                warnings=dict(Counter(r[16] for r in warning_rows)),
                largest_message_intervals=sorted(gaps, key=lambda x:x['days_between_messages'], reverse=True)[:5])


def write_review(sheets, spreadsheet, rows):
    tabs = metadata(sheets, spreadsheet); ensure_absent(tabs)
    used = {t['properties']['sheetId'] for t in tabs}
    sid = secrets.randbelow(2**30)
    while sid in used: sid = secrets.randbelow(2**30)
    data = [HEADERS] + rows
    area = dict(sheetId=sid, startRowIndex=0, endRowIndex=len(data), startColumnIndex=0, endColumnIndex=len(HEADERS))
    # Explicit stringValue prevents email content from becoming a spreadsheet formula.
    requests = [
        {'addSheet': {'properties': {'sheetId': sid, 'title': TITLE, 'gridProperties': {
            'rowCount': max(100, len(data)), 'columnCount': len(HEADERS), 'frozenRowCount': 1, 'frozenColumnCount': 1}}}},
        {'updateCells': {'start': {'sheetId': sid, 'rowIndex': 0, 'columnIndex': 0},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': str(v)}} for v in row]} for row in data], 'fields': 'userEnteredValue'}},
        {'repeatCell': {'range': area, 'cell': {'userEnteredFormat': {'wrapStrategy': 'CLIP', 'verticalAlignment': 'TOP'}}, 'fields': 'userEnteredFormat'}},
        {'repeatCell': {'range': {**area, 'endRowIndex': 1}, 'cell': {'userEnteredFormat': {
            'backgroundColor': {'red': .92, 'green': .92, 'blue': .92}, 'textFormat': {'bold': True}, 'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat'}},
        {'setBasicFilter': {'filter': {'range': area}}},
        {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': len(HEADERS)}, 'properties': {'pixelSize': 180}, 'fields': 'pixelSize'}},
        {'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1}, 'properties': {'pixelSize': 48}, 'fields': 'pixelSize'}},
    ]
    # One atomic create/populate request; never retry a write with an uncertain outcome.
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet, body={'requests': requests}).execute(num_retries=0)
    actual = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet,
        range=f"'{TITLE}'!A1:X{len(data)}").execute(num_retries=2).get('values', [])
    normalized = [row + ['']*(len(HEADERS)-len(row)) for row in actual]
    if normalized != data: raise RuntimeError('Review written but read-back verification failed. Do not rerun; inspect tab.')
    return sid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Create and populate the review tab after retrieval')
    args = parser.parse_args()
    config = load_config(); gmail, sheets = clients(config)
    ensure_absent(metadata(sheets, config['spreadsheet_id']))
    ids, rows = fetch_rows(gmail)
    report = summary(ids, rows)
    # Parsed private review snapshot only; never save MIME/.eml files or OAuth secrets.
    private_write(LOCAL/'review.json', json.dumps({'headers': HEADERS, 'rows': rows, 'report': report}, indent=2))
    if args.write:
        report['sheet_id'] = write_review(sheets, config['spreadsheet_id'], rows)
        report['verified'] = True
    private_write(LOCAL/'report.json', json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        # API exceptions can contain private content; only local RuntimeErrors are shown.
        print(str(exc) if type(exc) is RuntimeError else f'Operation failed ({type(exc).__name__}); no automatic write retry. Inspect review tab before retrying.')
        raise SystemExit(1)
