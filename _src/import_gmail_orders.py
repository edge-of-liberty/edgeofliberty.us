"""Atomic, order-level Gmail import into DOWNLOAD orders; no website operations."""
import collections
from decimal import Decimal
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from order_email_review import fetch_rows, QUERY
import paypal_orders as paypal

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
        stats.update(checked=len(by_order), skipped=len(set(by_order) & existing),
                     order_ids=sorted(by_order))
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


def attention_messages(orders, planning, relevant):
    """Read-only homework for the orders scanned by the existing Gmail importer."""
    messages = []
    emails = set()
    for row in orders:
        if len(row) < 3 or row[2] not in relevant:
            continue
        if len(row) > 3 and row[3]:
            emails.add(str(row[3]).strip().casefold())
        error = re.match(r"^(#(?:N/A|REF!|VALUE!|DIV/0!|NAME\?|NUM!|ERROR!|SPILL!|CALC!|LOADING!))(?:$|[ (])", str(row[1]))
        if error:
            messages.append(f'⚠ Order {row[2]} has an unresolved Column B lookup ({error[1]})')
    # Live conditional formatting: =and(F1="",K1<>0). F is sitemap; K is 2026.
    for row in planning[9:]:
        row = list(row) + [''] * max(0, 44 - len(row))
        name = str(row[0]).strip()
        matched_email = any(str(row[i]).strip().casefold() in emails for i in (12, 43))
        if (name and not name.casefold().startswith('zz') and matched_email
                and row[5] == '' and row[10] not in ('', 0, '0')):
            messages.append(f'⚠ {name}: Planning Column F sitemap/setup unresolved (blank F with 2026 participation)')
    return list(dict.fromkeys(messages))


def read_attention(read, relevant):
    if not relevant:
        return []
    try:
        orders = read("'DOWNLOAD orders'!A:D", 'UNFORMATTED_VALUE')
        planning = read("'Craft Fair Planning'!A:AR", 'UNFORMATTED_VALUE')
        messages = attention_messages(orders, planning, set(relevant))
    except Exception:
        messages = ['⚠ Order/setup attention checks unavailable; manual review required']
    for message in messages:
        print(message)
    return messages


def merged_plan(before, primary, payments):
    """Exact invoice/line joins. Existing attendance/product edits remain authoritative."""
    rows=[list(row)+['']*max(0,64-len(row)) for row in before]
    last=max((i for i,row in enumerate(rows,1) if any(row[2:])),default=1)
    updates={};new=[];warnings=[]
    def put(index,column,value):
        if rows[index][column]!=value:
            rows[index][column]=value;updates[index,column]=value
    def append(oid):
        index=last+len(new)
        while len(rows)<=index:rows.append(['']*64)
        if any(rows[index]):raise RuntimeError('Append destination is not empty')
        new.append(index);put(index,2,oid)
        return index
    grouped=collections.defaultdict(list)
    for r in primary:grouped[r[0]].append(r)
    for oid,items in grouped.items():
        existing=[i for i,row in enumerate(rows[1:],1) if row[2]==oid]
        if existing and len(existing)!=len(items):raise RuntimeError('Ambiguous existing line items for '+oid)
        for r in items:
            candidates=[i for i in existing if rows[i][41]==r[7]]
            if len(existing)==1 and len(items)==1:candidates=existing
            if existing:
                if len(candidates)!=1:raise RuntimeError('Ambiguous GoDaddy line join for '+oid)
                index=candidates[0]
            else:index=append(oid)
            provisional_date=None
            if rows[index][50] and not rows[index][3] and rows[index][52]:
                provisional_date=sheets_date(datetime.strptime(rows[index][52],'%b %d, %Y').date().isoformat())
            source={3:r[1],4:sheets_date(r[2]),6:r[3],26:r[5],27:r[4],38:r[13],40:r[6],41:r[7],44:r[8]}
            for col,value in source.items():
                if rows[index][col]=='' or (col==4 and provisional_date is not None and rows[index][col]==provisional_date):put(index,col,value)
    for oid,payment in payments.items():
        if oid in grouped and oid not in {row[2] for row in before[1:] if len(row)>2}:
            source=grouped[oid]
            for item in payment['items']:
                matching=[r for r in source if r[7]==item['sku']]
                if len(matching)!=1 or any(matching[0][col] and Decimal(matching[0][col].replace(',',''))!=Decimal(item[key]) for col,key in [(9,'unit'),(10,'total')]):
                    raise RuntimeError('GoDaddy/PayPal amounts or products conflict for '+oid)
            if any(r[12] and Decimal(r[12].replace(',',''))!=Decimal(payment['total']) for r in source):
                raise RuntimeError('GoDaddy/PayPal order total conflicts for '+oid)
        existing=[i for i,row in enumerate(rows[1:],1) if row[2]==oid]
        if not existing:
            for item in payment['items']:
                index=append(oid)
                for col,value in {4:sheets_date(payment['order_date']),6:'Paid',40:item['title'],41:item['sku'],44:item['qty']}.items():put(index,col,value)
            existing=[i for i,row in enumerate(rows[1:],1) if row[2]==oid]
        if len(existing)!=len(payment['items']):raise RuntimeError('PayPal line count conflicts for '+oid)
        used=set()
        for item in payment['items']:
            candidates=[i for i in existing if rows[i][41]==item['sku'] and i not in used]
            if len(existing)==1 and len(payment['items'])==1:candidates=existing
            if len(candidates)!=1:raise RuntimeError('Ambiguous PayPal line join for '+oid)
            index=candidates[0];used.add(index)
            # New two-source orders must agree on product/quantity. Older manual edits are retained.
            if index in new and (rows[index][41]!=item['sku'] or str(rows[index][44])!=item['qty']):
                raise RuntimeError('GoDaddy/PayPal products conflict for '+oid)
            existing_transaction=rows[index][53]
            if existing_transaction and existing_transaction!=payment['transaction']:
                raise RuntimeError('Different PayPal transaction already recorded for '+oid)
            supplemental=paypal.values(payment,item,rows[index])
            for col,value in enumerate(supplemental,50):put(index,col,value)
            if not rows[index][3]:warnings.append(f'⚠ Order {oid}: PayPal received; GoDaddy reservation identity missing — manual vendor review required')
    return rows,updates,new,list(dict.fromkeys(warnings))


def process(dry_run=False, report=None):
    report=report or (lambda result:None)
    report({'status':'before_write','orders':[]})
    from order_email_review import clients
    from google_sheets import load_config
    config=load_config();gmail,sheets=clients(config);book=config['spreadsheet_id']
    assert gmail.users().getProfile(userId='me').execute()['emailAddress']=='admin@batshitcrazyfarms.com'
    def properties():
        tabs=sheets.spreadsheets().get(spreadsheetId=book,fields='sheets(properties)').execute(num_retries=2)['sheets']
        return next(t['properties'] for t in tabs if t['properties']['sheetId']==config['orders_sheet_id'])
    def read(area,mode='FORMULA'):
        return sheets.spreadsheets().values().get(spreadsheetId=book,range=area,valueRenderOption=mode).execute(num_retries=2).get('values',[])
    prop=properties();assert prop['title']=='DOWNLOAD orders'
    if prop['gridProperties']['columnCount']<64:raise RuntimeError('PayPal columns AY:BL are missing')
    area=f"'DOWNLOAD orders'!A1:BL{prop['gridProperties']['rowCount']}"
    before=read(area)
    if not before or before[0][50:64]!=paypal.HEADERS:raise RuntimeError('PayPal headers AY:BL differ; manual review required')
    existing={r[2] for r in before[1:] if len(r)>2 and r[2]}
    # A delayed GoDaddy email can complete an earlier PayPal-only row, without a duplicate.
    incomplete={r[2] for r in before[1:] if len(r)>50 and r[50] and not r[3]}
    query,start,end=lookback();stats={'range':f'{start:%Y-%m-%d %H:%M:%S %Z} through {end:%Y-%m-%d %H:%M:%S %Z}'}
    print(f"Email lookback (45 days): {stats['range']}",flush=True)
    primary=prepare(gmail,existing-incomplete,stats=stats,query=query)
    payments=paypal.fetch(gmail,query.replace(QUERY,'subject:"Notification of payment received"'))
    relevant=set(stats.get('order_ids',[]))|set(payments)
    planned,updates,new,warnings=merged_plan(before,primary,payments)
    last=max((i for i,r in enumerate(before,1) if any(r[2:])),default=1)
    new_ids=list(dict.fromkeys(planned[i][2] for i in new))
    if dry_run:
        print(f'Would append {len(new)} rows and annotate {len({i for i,c in updates}-set(new))} existing rows')
        report({'status':'dry_run','orders':[],'warnings':warnings});return
    if updates:
        if properties()!=prop or read(area)!=before:raise RuntimeError('Orders changed during preview; no write attempted')
        fields='sheets(data(startRow,startColumn,rowData(values(userEnteredValue,userEnteredFormat,note,dataValidation))))'
        def entered():return sheets.spreadsheets().get(spreadsheetId=book,ranges=[area],fields=fields).execute(num_retries=2)
        original=entered()
        requests=[]
        if last+len(new)>prop['gridProperties']['rowCount']:
            requests.append({'appendDimension':{'sheetId':prop['sheetId'],'dimension':'ROWS','length':last+len(new)-prop['gridProperties']['rowCount']}})
        if new:
            if len(before[last-1])<2 or not all(str(v).startswith('=') for v in before[last-1][:2]):raise RuntimeError('Last row formulas missing')
            requests.append({'copyPaste':{'source':{'sheetId':prop['sheetId'],'startRowIndex':last-1,'endRowIndex':last,'startColumnIndex':0,'endColumnIndex':2},'destination':{'sheetId':prop['sheetId'],'startRowIndex':last,'endRowIndex':last+len(new),'startColumnIndex':0,'endColumnIndex':2},'pasteType':'PASTE_FORMULA','pasteOrientation':'NORMAL'}})
            formats=sheets.spreadsheets().get(spreadsheetId=book,ranges=[f"'DOWNLOAD orders'!E{last}"],fields='sheets(data(rowData(values(effectiveFormat.numberFormat))))').execute(num_retries=2)
            cell=formats['sheets'][0].get('data',[{}])[0].get('rowData',[{}])[0].get('values',[{}])[0]
            fmt=cell.get('effectiveFormat',{}).get('numberFormat',{})
            pattern=fmt.get('pattern','yyyy-mm-dd') if fmt.get('type')=='DATE' else 'yyyy-mm-dd'
            requests.append({'repeatCell':{'range':{'sheetId':prop['sheetId'],'startRowIndex':last,'endRowIndex':last+len(new),'startColumnIndex':4,'endColumnIndex':5},'cell':{'userEnteredFormat':{'numberFormat':{'type':'DATE','pattern':pattern}}},'fields':'userEnteredFormat.numberFormat'}})
            requests.append({'repeatCell':{'range':{'sheetId':prop['sheetId'],'startRowIndex':last,'endRowIndex':last+len(new),'startColumnIndex':0,'endColumnIndex':42},'cell':{'userEnteredFormat':{'backgroundColor':COLOR}},'fields':'userEnteredFormat.backgroundColor'}})
        for (index,column),value in sorted(updates.items()):
            requests.append({'updateCells':{'start':{'sheetId':prop['sheetId'],'rowIndex':index,'columnIndex':column},'rows':[{'values':[{'userEnteredValue':{'numberValue':value} if isinstance(value,(int,float)) else {'stringValue':str(value)}}]}],'fields':'userEnteredValue'}})
        report({'status':'write_attempted','orders':[]})
        sheets.spreadsheets().batchUpdate(spreadsheetId=book,body={'requests':requests}).execute(num_retries=0)
        after=read(f"'DOWNLOAD orders'!A1:BL{max(prop['gridProperties']['rowCount'],last+len(new))}")
        for index in range(len(planned)):
            actual=(after[index] if index<len(after) else [])+['']*64
            expected=planned[index]
            for column in range(2 if index in new else 0,64):
                assert actual[column]==expected[column],(index+1,column+1)
            if index in new:assert all(str(actual[c]).startswith('=') for c in (0,1))
        verified=entered()
        def native_cells(data):
            cells={}
            for tab in data.get('sheets',[]):
                for block in tab.get('data',[]):
                    for i,row in enumerate(block.get('rowData',[]),block.get('startRow',0)):
                        for col,cell in enumerate(row.get('values',[]),block.get('startColumn',0)):
                            cell=dict(cell)
                            if (i,col) in updates:cell.pop('userEnteredValue',None)
                            if cell:cells[i,col]=cell
            return cells
        # Appended-row formatting is intentional; all earlier cell metadata is preserved.
        old={key:value for key,value in native_cells(original).items() if key[0] not in new}
        now={key:value for key,value in native_cells(verified).items() if key[0] not in new}
        assert old==now,'Existing cell formatting/formulas changed; manual review required'
    else:after=before
    warnings+=read_attention(read,relevant)
    warnings=list(dict.fromkeys(warnings))
    for warning in warnings:print(warning)
    print(f'Checked {len(relevant)} orders across GoDaddy/PayPal. Imported {len(new_ids)} orders / {len(new)} rows; enriched {len({i for i,c in updates}-set(new))} existing rows.')
    report({'status':'complete','warnings':warnings,'updated_orders':list(dict.fromkeys(planned[i][2] for i in sorted({i for i,c in updates}-set(new)))), 'orders':[{'id':oid,'skus':list(dict.fromkeys(planned[i][41] for i in new if planned[i][2]==oid)),'needs_vendor_setup':False} for oid in new_ids]})


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
    parser.add_argument('--result-file', help='Private machine-readable result for the Remote wrapper')
    args = parser.parse_args()
    if args.result_file:
        import json
        from pathlib import Path
        from google_sheets import private_write
        path = Path(args.result_file).resolve()
        local = Path(__file__).resolve().parents[1] / '_local/process-new-order'
        if not path.is_relative_to(local.resolve()):
            parser.error('Result file must be inside _local/process-new-order')
        process(args.dry_run, report=lambda result: private_write(path, json.dumps(result) + '\n'))
    else:
        process(args.dry_run)


if __name__=='__main__':
    main()
