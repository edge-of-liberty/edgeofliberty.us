"""Post-publish sitemap input sync. Default is offline preview; --write is explicit."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from google_sheets import get_credentials, load_config
from authorize_orders import ORDER_SCOPES

ROOT = Path(__file__).resolve().parents[1]
TITLE = 'DOWNLOAD sitemap.xml'
PATTERNS = {1: '=split(A{row},">")', 3: '=split(C{row},"<")', 6: '=split(D{row},"/")'}


def sitemap_lines(path):
    text = Path(path).read_text(encoding='utf-8')
    if text.startswith('---\n'):
        parts = text.split('---\n', 2)
        if len(parts) != 3: raise ValueError('Unclosed sitemap front matter')
        text = parts[2]
    root = ET.fromstring(text)
    if root.tag != '{http://www.sitemaps.org/schemas/sitemap/0.9}urlset':
        raise ValueError('Expected a sitemap urlset')
    # Existing row formulas require loc elements on separate rows, unlike the
    # compact generated XML. Whitespace between tags changes no sitemap content.
    return [line.strip() for line in re.sub(r'>\s*<', '>\n<', text).splitlines() if line.strip()]


def client():
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    import httplib2
    config = load_config()
    creds = get_credentials(config, scopes=ORDER_SCOPES, token_name='token-orders.json')
    return config, build('sheets','v4',http=AuthorizedHttp(creds,http=httplib2.Http(timeout=30)),cache_discovery=False)


def inspect(service, book):
    tabs=service.spreadsheets().get(spreadsheetId=book,fields='sheets(properties)').execute(num_retries=2)['sheets']
    prop=next(t['properties'] for t in tabs if t['properties']['title']==TITLE)
    area=f"'{TITLE}'!A1:G{prop['gridProperties']['rowCount']}"
    rows=service.spreadsheets().values().get(spreadsheetId=book,range=area,valueRenderOption='FORMULA').execute(num_retries=2).get('values',[])
    return prop, rows


def plan(lines, prop, rows):
    n=len(lines);sid=prop['sheetId'];capacity=prop['gridProperties']['rowCount']
    requests=[];report={'input_write':f'A1:A{n}','input_clear':None,'formula_fill':[], 'formula_clear':[], 'rows_to_add':max(0,n-capacity)}
    if n>capacity: requests.append({'appendDimension':{'sheetId':sid,'dimension':'ROWS','length':n-capacity}})
    def area(col,start,end):
        return {'sheetId':sid,'startRowIndex':start,'endRowIndex':end,'startColumnIndex':col,'endColumnIndex':col+1}
    requests.append({'updateCells':{'start':{'sheetId':sid,'rowIndex':0,'columnIndex':0},'rows':[{'values':[{'userEnteredValue':{'stringValue':line}}]} for line in lines],'fields':'userEnteredValue'}})
    old_a=max((i for i,r in enumerate(rows,1) if r and r[0]),default=0)
    if old_a>n:
        report['input_clear']=f'A{n+1}:A{old_a}'
        requests.append({'updateCells':{'range':area(0,n,old_a),'fields':'userEnteredValue'}})
    for col,pattern in PATTERNS.items():
        populated=[(i,r[col]) for i,r in enumerate(rows,1) if len(r)>col and r[col]]
        if not populated:raise ValueError('No existing formula template in '+chr(65+col))
        # Refuse to overwrite unexpected manual content or changed formula designs.
        for i,value in populated:
            if value.lower().replace(' ','')!=pattern.format(row=i).lower().replace(' ',''):
                raise ValueError(f'Unexpected formula/content in {chr(65+col)}{i}; inspect before syncing')
        source=populated[0][0];present={i for i,_ in populated};missing=[i for i in range(1,n+1) if i not in present]
        groups=[]
        for i in missing:
            if groups and groups[-1][1]==i-1:groups[-1][1]=i
            else:groups.append([i,i])
        for first,last in groups:
            requests.append({'copyPaste':{'source':area(col,source-1,source),'destination':area(col,first-1,last),'pasteType':'PASTE_FORMULA'}})
            report['formula_fill'].append(f'{chr(65+col)}{first}:{chr(65+col)}{last}')
        end=max(present)
        if end>n:
            requests.append({'updateCells':{'range':area(col,n,end),'fields':'userEnteredValue'}})
            report['formula_clear'].append(f'{chr(65+col)}{n+1}:{chr(65+col)}{end}')
    return report,requests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sitemap',type=Path,default=ROOT/'sitemap.xml')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--plan-live',action='store_true',help='Read live ranges and show plan without writing')
    mode.add_argument('--write',action='store_true')
    args=parser.parse_args();lines=sitemap_lines(args.sitemap)
    if not args.write and not args.plan_live:
        print(json.dumps({'rows':len(lines),'values':[[line] for line in lines]},indent=2));return
    config,service=client();book=config['spreadsheet_id'];prop,rows=inspect(service,book)
    report,requests=plan(lines,prop,rows);print(json.dumps(report,indent=2))
    if not args.write:return
    # Recheck before the single atomic write; never blindly retry uncertain writes.
    if inspect(service,book)!=(prop,rows):raise RuntimeError('Sitemap sheet changed during planning; no write')
    service.spreadsheets().batchUpdate(spreadsheetId=book,body={'requests':requests}).execute(num_retries=0)
    after_prop,after=inspect(service,book)
    assert [r[0] if r else '' for r in after[:len(lines)]]==lines
    for col,pattern in PATTERNS.items():
        assert all(len(r)>col and r[col].lower().replace(' ','')==pattern.format(row=i).lower().replace(' ','') for i,r in enumerate(after[:len(lines)],1))
    assert all(not any(r[c] for c in [0,1,3,6] if len(r)>c) for r in after[len(lines):])
    print(f'[OK] Sitemap input synchronized: {len(lines)} rows; existing formula patterns preserved.')


if __name__=='__main__':main()
