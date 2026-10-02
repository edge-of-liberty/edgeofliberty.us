"""Restore an audited attendance formula; never force an attendance/payment status."""
import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
import uuid
from vendor_absent import (ROOT, Stop, check_repositories, load_config, service,
                           snapshot, resolve, entered, private_write, run_logged)


def original_formula(target, directory):
    candidates=[]
    for path in directory.glob('*.json'):
        try:
            records=json.loads(path.read_text())
            # Only completed, verified absence overrides are authoritative.
            for record in records:
                t=record.get('target',{})
                if record.get('phase')!='before' or t.get('slug')!=target['slug'] or t.get('date')!=target['date']:
                    continue
                if not any(r.get('phase')=='verified' and r.get('target')==t for r in records):
                    continue
                prior=record.get('before',{})
                if prior=={'stringValue':'Absent'}:continue  # Idempotent repeat is not a new override.
                candidates.append((record['time'],t,prior))
        except (ValueError,KeyError,TypeError):
            raise Stop('Absence audit is unreadable; manual formula review required.') from None
    if not candidates:
        raise Stop('No verified original formula found; manual formula review required. Nothing changed.')
    candidates.sort(key=lambda item:item[0],reverse=True)
    stamp,old,value=candidates[0]
    if any(item[0]==stamp and item[1:]!=(old,value) for item in candidates[1:]):
        raise Stop('Conflicting absence audits; manual formula review required.')
    if old!=target:
        raise Stop('Vendor/date location changed since the override; original formula needs manual review.')
    if set(value)!={'formulaValue'} or not value['formulaValue'].startswith('='):
        raise Stop('Original value was not a lookup formula; manual formula review required. Nothing changed.')
    return value


def formula_from_below(api, config, target):
    source={**target, 'row':target['row']+1}
    value=entered(api,config,source)
    formula=value.get('formulaValue','')
    if not formula.startswith('=') or not re.search(r'\b(?:VLOOKUP|XLOOKUP|LOOKUP|MATCH|SUMIFS|COUNTIFS)\s*\(',formula,re.I):
        raise Stop('Cell below is not a recognized lookup formula; manual review required.')
    # Conservative A1 translator: preserve quoted strings/sheet names and absolute rows.
    # Unsupported dynamic/whole-row references require review rather than guessing.
    parts=re.split(r'("(?:[^"]|"")*"|\'(?:[^\']|\'\')*\')',formula)
    own_row=False
    def shift(match):
        nonlocal own_row
        col,absolute,row=match.groups()
        if absolute:return match.group(0)
        number=int(row)
        if number==source['row']+1:own_row=True
        if number<=1:raise Stop('Relative reference would leave the sheet; manual review required.')
        return col+str(number-1)
    for i in range(0,len(parts),2):
        if re.search(r'\b(?:INDIRECT|OFFSET)\s*\(|\d+\s*:\s*\$?\d+|[\[\]]',parts[i],re.I):
            raise Stop('Unsupported formula references; manual review required.')
        parts[i]=re.sub(r'(?<![A-Za-z0-9_])(?!(?:[A-Za-z]+[0-9]+)!)'
                        r'(\$?[A-Za-z]{1,3})(\$?)([0-9]+)(?![A-Za-z0-9_]|\s*\()',shift,parts[i])
    if not own_row:raise Stop('Formula below does not reference its own row; manual review required.')
    return {'formulaValue':''.join(parts)},source,value


def restore(api,config,vendor,day,audit,from_below=False):
    target=resolve(snapshot(api,config),vendor,day,config['year'])
    source=None
    if from_below:
        formula,source,source_value=formula_from_below(api,config,target)
    else:
        formula=original_formula(target,ROOT/'_local/vendor-absent')
    before=entered(api,config,target)
    if before not in ({'stringValue':'Absent'},formula):
        raise Stop('Cell is no longer the Absent override or original formula; nothing changed.')
    audit({'phase':'before','target':target,'before':before,'restore':formula})
    if resolve(snapshot(api,config),vendor,day,config['year'])!=target or entered(api,config,target)!=before:
        raise Stop('Planning changed during verification; nothing changed.')
    if source is not None:
        audit({'phase':'source_below','source':source,'formula':source_value,'restore':formula})
        if entered(api,config,source)!=source_value:
            raise Stop('Source formula changed; nothing changed.')
    if before!=formula:
        request={'updateCells':{'range':{'sheetId':config['planning_sheet_id'],
            'startRowIndex':target['row'],'endRowIndex':target['row']+1,
            'startColumnIndex':target['column'],'endColumnIndex':target['column']+1},
            'rows':[{'values':[{'userEnteredValue':formula}]}],'fields':'userEnteredValue'}}
        try:
            api.spreadsheets().batchUpdate(spreadsheetId=config['spreadsheet_id'],
                body={'requests':[request]}).execute(num_retries=0)
        except Exception:
            if entered(api,config,target)!=formula:
                raise Stop('Formula write failed or is uncertain; inspect the cell. No rollback attempted.') from None
    if entered(api,config,target)!=formula:
        raise Stop('Formula readback differs; stopped without rollback.')
    if resolve(snapshot(api,config),vendor,day,config['year'])!=target:
        raise Stop('Planning changed after restoration; manual verification required. No rollback attempted.')
    if source is not None and entered(api,config,source)!=source_value:
        raise Stop('Source cell changed during restoration; manual review required. No rollback attempted.')
    audit({'phase':'verified','target':target,'after':formula})
    return target


def run(vendor,day,from_below=False):
    check_repositories()
    config=load_config();api=service(config)
    path=ROOT/'_local/revert-absent'/f'{uuid.uuid4().hex}.json';records=[]
    def audit(record):
        records.append({'time':datetime.now(timezone.utc).isoformat(),**record})
        private_write(path,json.dumps(records,indent=2)+'\n')
    target=restore(api,config,vendor,day,audit,from_below=True) if from_below else restore(api,config,vendor,day,audit)
    try:
        run_logged(['bash','-c','./_src/process_orders.sh && ./_src/build.sh all'], check=True)
    except Exception as exc:
        raise Stop(f"{target['name']} — {target['date']} formula restored; rebuild/push failed. Formula retained. {exc}") from None
    audit({'phase':'published','target':target})
    print(f"✓ {target['name']} — {target['date']} formula restored\n✓ Site rebuilt and published")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor',required=True);parser.add_argument('--date',required=True)
    parser.add_argument('--from-below',action='store_true',help='Explicitly authorized lookup formula from the cell below')
    args=parser.parse_args()
    try:run(args.vendor,args.date,from_below=args.from_below)
    except (Stop,OSError,subprocess.SubprocessError) as exc:
        print(f'⚠ {exc}');return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
