"""Remote production refresh using the existing importer; no alternate import logic."""
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
from vendor_absent import ROOT, CHH, Stop, check_repositories


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
        return result
    except (OSError,ValueError,KeyError,TypeError):
        raise Stop('Importer result unavailable or uncertain. Manual review required; no build run.') from None


def publication_targets(root=ROOT, chh=CHH):
    # Compare current generated output, never infer attendance from payment or SKU.
    targets = [('https://www.createhappinesshouse.com/', [(chh/'index.html').read_text().strip()])]
    home = [(root/'_includes'/name).read_text().strip() for name in ('home_dates.html','home_vendors.html')]
    targets.append(('https://www.edgeofliberty.us/', home))
    data=json.loads((root/'_data/build.json').read_text())
    for slug in data['dates']:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug):raise Stop('Invalid generated date slug.')
        text=(root/slug/'index.html').read_text()
        body=re.sub(r'^---\n.*?\n---\n','',text,flags=re.S)
        chunks=[c.strip() for c in re.split(r'{%.*?%}|{{.*?}}',body,flags=re.S) if c.strip()]
        targets.append((f'https://www.edgeofliberty.us/{slug}/',chunks))
    redirect=(root/'craft-fair/index.html').read_text()
    links=re.findall(r'url=(https://www\.edgeofliberty\.us/[a-z0-9-]+/)',redirect,re.I)
    if not links:raise Stop('Cannot verify generated next-fair redirect.')
    targets.append(('https://www.edgeofliberty.us/craft-fair/',links))
    return targets


def matches_live(target):
    url,chunks=target
    response=subprocess.run(['curl','--fail','--silent','--show-error','--max-time','15',url],
                            text=True,capture_output=True)
    return response.returncode==0 and all(chunk in response.stdout for chunk in chunks)


def verify_publication():
    pending=publication_targets()
    for attempt in range(6):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(matches_live,pending))
        pending=[target for target,ok in zip(pending,results) if not ok]
        if not pending:return
        if attempt<5:time.sleep(10)
    raise Stop('Push completed; live refresh not yet verified. No imported orders were undone.')


def run():
    check_repositories()
    path=ROOT/'_local/process-new-order'/f'{uuid.uuid4().hex}.json'
    imported=subprocess.run(['./_src/process_orders.sh','--result-file',str(path)],cwd=ROOT)
    result=read_result(path)
    if imported.returncode:
        if result['status']=='before_write':
            raise Stop('Order processing stopped before writing. No changes made; manual review required.')
        raise Stop('Order import failed or write result is uncertain. Manual review required; no build run. Nothing undone.')
    if result['status']=='needs_vendor_setup':
        ids=', '.join(o['id'] for o in result['orders'] if o['needs_vendor_setup'])
        raise Stop(f'Order(s) {ids} imported; vendor setup required. No build run; imported orders retained.')
    if result['status']!='complete':
        raise Stop('Importer result is uncertain. Manual review required; no build run.')
    try:
        subprocess.run(['./_src/build.sh','all'],cwd=ROOT,check=True)
        check_repositories()
        verify_publication()
    except Exception as exc:
        raise Stop(f'{imported_label(result)}; refresh/publish verification failed. Imported orders retained. {exc}') from None
    print(f'✓ {imported_label(result)}\n✓ Site refreshed and published')


def main():
    try:run()
    except (Stop,OSError,subprocess.SubprocessError) as exc:
        print(f'⚠ {exc}')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
