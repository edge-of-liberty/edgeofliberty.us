"""Atomic, order-level Gmail import into DOWNLOAD orders; no website operations."""
import collections
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from order_email_review import fetch_rows, QUERY

COLOR = {'red': 217/255, 'green': 234/255, 'blue': 247/255}


def lookback(now=None):
    end = now or datetime.now(ZoneInfo("America/Chicago"))
    start = end - timedelta(days=45)
    query = f'{QUERY} after:{int(start.timestamp())-1} before:{int(end.timestamp())+1}'
    return query, start, end


def prepare(gmail, existing, allowed=None, stats=None, query=QUERY):
    _, rows = fetch_rows(gmail, query)
    by_order = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        if allowed is None or row[0] in allowed:
            by_order[row[0]][row[17]].append(row)
    if stats is not None:
        stats.update(checked=len(by_order), skipped=len(set(by_order) & existing))
    result = []
    for oid, messages in by_order.items():
        if oid in existing: continue
        variants = list(messages.values())
        signature = lambda rr: [tuple(r[:16]) for r in rr]
        if any(signature(v) != signature(variants[0]) for v in variants[1:]):
            raise RuntimeError('Conflicting notifications for ' + oid)
        for r in variants[0]:
            if r[16] or not re.fullmatch(r'R\d+', r[0]) or not all(r[i] for i in [1,2,4,7,8]):
                raise RuntimeError('Incomplete/ambiguous order ' + oid)
            sheets_date(r[2])  # Validate before any write.
            result.append(r)
    return sorted(result, key=lambda r:(r[2],r[0]))


def sheets_date(value):
    return (date.fromisoformat(value) - date(1899, 12, 30)).days


def requests_for(rows, sid, last, grid_rows, date_pattern='yyyy-mm-dd'):
    """last is the one-based last populated row. Only append destinations touched."""
    requests = []
    if last + len(rows) > grid_rows:
        requests.append({'appendDimension': {'sheetId':sid,'dimension':'ROWS','length':last+len(rows)-grid_rows}})
    requests.append({'copyPaste': {
        'source': {'sheetId':sid,'startRowIndex':last-1,'endRowIndex':last,'startColumnIndex':0,'endColumnIndex':2},
        'destination': {'sheetId':sid,'startRowIndex':last,'endRowIndex':last+len(rows),'startColumnIndex':0,'endColumnIndex':2},
        'pasteType':'PASTE_FORMULA','pasteOrientation':'NORMAL'}})
    for offset,r in enumerate(rows):
        for col,values in [(2,[r[0],r[1],r[2],'',r[3]]),(26,[r[5],r[4]]),(41,[r[7]])]:
            requests.append({'updateCells':{'start':{'sheetId':sid,'rowIndex':last+offset,'columnIndex':col},
                'rows':[{'values':[{'userEnteredValue':({'numberValue':sheets_date(v)} if col+j==4 else {'stringValue':v})} for j,v in enumerate(values)]}],
                'fields':'userEnteredValue'}})
    requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':last,'endRowIndex':last+len(rows),'startColumnIndex':4,'endColumnIndex':5},
        'cell':{'userEnteredFormat':{'numberFormat':{'type':'DATE','pattern':date_pattern}}},'fields':'userEnteredFormat.numberFormat'}})
    requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':last,'endRowIndex':last+len(rows),'startColumnIndex':0,'endColumnIndex':42},
        'cell':{'userEnteredFormat':{'backgroundColor':COLOR}},'fields':'userEnteredFormat.backgroundColor'}})
    return requests


def process(dry_run=False):
    from order_email_review import clients
    from google_sheets import load_config
    config = load_config()
    gmail, sheets = clients(config)
    book = config['spreadsheet_id']
    assert gmail.users().getProfile(userId='me').execute()['emailAddress'] == 'admin@batshitcrazyfarms.com'
    def properties():
        tabs = sheets.spreadsheets().get(spreadsheetId=book, fields='sheets(properties)').execute(num_retries=2)['sheets']
        return next(t['properties'] for t in tabs if t['properties']['sheetId']==config['orders_sheet_id'])
    def read(area, mode='FORMULA'):
        return sheets.spreadsheets().values().get(spreadsheetId=book,range=area,valueRenderOption=mode).execute(num_retries=2).get('values',[])
    prop=properties()
    assert prop['title']=='DOWNLOAD orders'
    area=f"'DOWNLOAD orders'!A1:AX{prop['gridProperties']['rowCount']}"
    before=read(area)
    existing={r[2].strip() for r in before[1:] if len(r)>2}
    stats = {}
    query, start, end = lookback()
    stats["range"] = f"{start:%Y-%m-%d %H:%M:%S %Z} through {end:%Y-%m-%d %H:%M:%S %Z}"
    print(f"Gmail lookback (45 days): {stats['range']}", flush=True)
    rows = prepare(gmail, existing, stats=stats, query=query)
    if dry_run or not rows:
        print_summary(stats, rows, dry_run)
        if dry_run:
            for oid in dict.fromkeys(r[0] for r in rows):
                items = [r for r in rows if r[0] == oid]
                print(f"PENDING: {oid} — {items[0][2]} — {len(items)} line-item row(s)")
        return
    # Recheck live data after Gmail retrieval and immediately before mutation.
    prop=properties()
    new_area=f"'DOWNLOAD orders'!A1:AX{prop['gridProperties']['rowCount']}"
    current=read(new_area)
    if current!=before:raise RuntimeError('Orders changed during preview; stopped.')
    last=max(i for i,r in enumerate(current,1) if any(r[2:]))
    if not all(str(x).startswith('=') for x in current[last-1][:2]) or len(current[last-1][:2])!=2:
        raise RuntimeError('Last populated row does not contain both formulas.')
    if any(any(r) for r in current[last:last+len(rows)]):
        raise RuntimeError('Append destination is not empty.')
    # Preserve all existing entered values/formulas/formats/notes/validation as evidence.
    fields='sheets(data(rowData(values(userEnteredValue,userEnteredFormat,note,dataValidation))))'
    def entered():
        return sheets.spreadsheets().get(spreadsheetId=book,ranges=[f"'DOWNLOAD orders'!A1:AX{last}"],fields=fields).execute(num_retries=2)
    original=entered()
    formats=sheets.spreadsheets().get(spreadsheetId=book,ranges=[f"'DOWNLOAD orders'!E{last}"],fields='sheets(data(rowData(values(effectiveFormat.numberFormat))))').execute(num_retries=2)
    cell=formats['sheets'][0].get('data',[{}])[0].get('rowData',[{}])[0].get('values',[{}])[0]
    fmt=cell.get('effectiveFormat',{}).get('numberFormat',{})
    pattern=fmt.get('pattern','yyyy-mm-dd') if fmt.get('type')=='DATE' else 'yyyy-mm-dd'
    print(f'Appending {len(rows)} rows at {last+1}:{last+len(rows)}; copying A{last}:B{last}.',flush=True)
    sheets.spreadsheets().batchUpdate(spreadsheetId=book,body={'requests':requests_for(rows,prop['sheetId'],last,prop['gridProperties']['rowCount'],pattern)}).execute(num_retries=0)
    if entered()!=original:raise RuntimeError('Existing-row verification differs; stop and inspect.')
    after=read(f"'DOWNLOAD orders'!A1:AX{last+len(rows)}")
    appended=after[last:]
    effective=read(f"'DOWNLOAD orders'!A{last+1}:B{last+len(rows)}",'UNFORMATTED_VALUE')
    for i,(actual,r) in enumerate(zip(appended,rows)):
        actual=actual+['']*(50-len(actual))
        expected={2:r[0],3:r[1],4:sheets_date(r[2]),5:'',6:r[3],26:r[5],27:r[4],41:r[7]}
        assert all(actual[k]==v for k,v in expected.items())
        assert all(str(actual[k]).startswith('=') for k in [0,1])
        assert all(not actual[k] for k in range(2,50) if k not in expected)
        assert effective[i][0]==r[7].split('-')[0]+r[1]
        assert len(effective[i])==2
        # A preserved lookup may legitimately report an unmatched vendor.
        # Report this below; never rewrite Planning or retry an already-written order.
    expected_counts = collections.Counter(r[0] for r in rows)
    count=collections.Counter(r[2] for r in after[1:] if len(r)>2 and r[2] in expected_counts)
    assert len(appended)==len(rows) and count==expected_counts
    color_data=sheets.spreadsheets().get(spreadsheetId=book,ranges=[f"'DOWNLOAD orders'!A{last+1}:AP{last+len(rows)}"],fields='sheets(data(rowData(values(userEnteredFormat.backgroundColor))))').execute(num_retries=2)
    for row in color_data['sheets'][0]['data'][0]['rowData']:
        assert len(row['values'])==42
        for cell in row['values']:
            assert all(abs(cell['userEnteredFormat']['backgroundColor'][k]-v)<.001 for k,v in COLOR.items())
    print_summary(stats, rows)
    for warning in missing_vendor_messages(rows, effective):
        print(warning)


def print_summary(stats, rows, dry_run=False):
    verb = 'Would import' if dry_run else 'Imported'
    print(f"Checked {stats['checked']} Gmail orders in the lookback. "
          f"{verb} {len({r[0] for r in rows})} orders / {len(rows)} line-item rows. "
          f"Skipped {stats['skipped']} orders already in DOWNLOAD orders.")


def missing_vendor_messages(rows, effective):
    missing = {r[0] for r, value in zip(rows, effective) if len(value)>1 and value[1]=='#N/A'}
    messages = []
    for oid in sorted(missing):
        items = [r for r in rows if r[0]==oid]
        first = items[0]
        company = ' '.join(first[13].split()) or '(company name not provided)'
        skus = ', '.join(dict.fromkeys(r[7] for r in items))
        messages.append(f'NEW VENDOR NEEDS SETUP: {company} — {first[1]} — {oid} — {skus} — {first[3]}')
    return messages


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Read and report only; never write Sheets')
    args = parser.parse_args()
    process(args.dry_run)


if __name__=='__main__':
    main()
