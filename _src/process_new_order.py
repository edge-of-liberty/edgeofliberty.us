"""Remote production refresh using the existing importer; no alternate import logic."""
import json
import re
import subprocess
import uuid
from vendor_absent import ROOT, Stop, check_repositories, run_logged


def imported_label(result):
    ids = [o['id'] for o in result['orders']]
    return ('No new orders' if not ids else
            ('Order ' + ids[0] + ' processed' if len(ids)==1 else 'Orders ' + ', '.join(ids) + ' processed'))


def read_result(path):
    try:
        result=json.loads(path.read_text())
        if result['status'] not in ('before_write','write_attempted','needs_vendor_setup','complete'):
            raise ValueError()
        orders=result['orders']
        if not isinstance(orders,list):raise ValueError()
        for order in orders:
            if not re.fullmatch(r'R\d+',order['id']) or not isinstance(order['skus'],list):raise ValueError()
        warnings = result.get('warnings', [])
        if not isinstance(warnings, list) or not all(isinstance(v, str) for v in warnings):
            raise ValueError()
        return result
    except (OSError,ValueError,KeyError,TypeError):
        raise Stop('Importer result unavailable or uncertain. Manual order review required.') from None


def order_outcome(result, returncode):
    if result['status']=='complete' and returncode==0:
        return '\n'.join(['✓ ' + imported_label(result), *result.get('warnings', [])])
    if result['status']=='needs_vendor_setup':
        ids=', '.join(o['id'] for o in result['orders'])
        return '\n'.join([f'⚠ Order(s) {ids} written to DOWNLOAD orders; vendor setup requires manual review', *result.get('warnings', [])])
    if result['status']=='before_write':
        return '⚠ Order processing requires manual review — no orders written by this run'
    return '⚠ Order write result uncertain; manual review required — nothing undone'


def run():
    check_repositories()
    path=ROOT/'_local/process-new-order'/f'{uuid.uuid4().hex}.json'
    try:
        imported=run_logged(['./_src/process_orders.sh','--result-file',str(path)])
        outcome=order_outcome(read_result(path), imported.returncode)
    except Exception:
        outcome='⚠ Order processing failed or result uncertain; manual review required — nothing undone'
    # Order problems never skip refresh. Recheck publication safety after processing.
    try:
        check_repositories()
        run_logged(['./_src/build.sh','all'], check=True)
    except Exception as exc:
        raise Stop(f'{outcome}\n⚠ Site refresh/push failed: {exc}') from None
    print(f'{outcome}\n✓ Site refreshed and published using current Planning data')


def main():
    try:run()
    except (Stop,OSError,subprocess.SubprocessError) as exc:
        print(f'⚠ {exc}')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
