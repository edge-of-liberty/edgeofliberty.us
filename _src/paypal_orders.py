"""PayPal evidence for the existing importer, never an independent importer."""
import base64
import re
from datetime import datetime, timedelta
from decimal import Decimal
from order_email_review import text_from_mime

HEADERS = ['PayPal email','PayPal payer name / business','PayPal payment date',
           'PayPal transaction ID','PayPal order total','PayPal currency',
           'PayPal item description','PayPal item ID','PayPal quantity',
           'PayPal unit price','PayPal line total','PayPal merchant instructions',
           'PayPal source email','PayPal comparison notes']


def parse(mid, timestamp, raw):
    message, text = text_from_mime(raw)
    if str(message.get('Subject','')).strip() != 'Notification of payment received':
        raise RuntimeError('Unexpected PayPal notification subject')
    if 'Payment sent to paypal@batshitcrazyfarms.com' not in text:
        raise RuntimeError('PayPal payment recipient not recognized')
    def field(label):
        match = re.search(r'^'+re.escape(label)+r'\s*\n([^\n]+)',text,re.M)
        return match[1].strip() if match else ''
    invoice = field('Invoice ID')
    buyer = re.search(r'^Buyer\n([^\n]+)\n([^\n]+)',text,re.M)
    amount = re.search(r'You received a payment of \$([\d,.]+)\s+([A-Z]{3})',text)
    if not re.fullmatch(r'R\d+',invoice) or not buyer or not amount or not field('Transaction ID'):
        raise RuntimeError('Incomplete PayPal payment '+(invoice or mid))
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',buyer[2].strip()):
        raise RuntimeError('PayPal payer email not recognized for '+invoice)
    datetime.strptime(field('Transaction date'),'%b %d, %Y')
    items = []
    for match in re.finditer(r'^([^\n]+)\nItem# ([^\n]+)\n\$([\d,.]+)\s+([A-Z]{3})\n(\d+)\n\$([\d,.]+)\s+([A-Z]{3})',text,re.M):
        title = match[1]
        day = re.fullmatch(r'Edge of Liberty Craft Fair ([A-Za-z]{3} \d{2}, \d{4})',title)
        if not day:
            raise RuntimeError('Unrecognized PayPal product for '+invoice)
        sku = datetime.strptime(day[1],'%b %d, %Y').strftime('%y%m%d')
        unit, qty, total = match[3].replace(',',''), int(match[5]), match[6].replace(',','')
        if qty < 1 or Decimal(unit)*qty != Decimal(total) or match[4] != amount[2] or match[7] != amount[2]:
            raise RuntimeError('Conflicting PayPal item amounts for '+invoice)
        items.append(dict(sku=sku,title=title,item_id=match[2],unit=unit,qty=str(qty),total=total))
    if not items or len({i['sku'] for i in items}) != len(items) or sum(Decimal(i['total']) for i in items) != Decimal(amount[1].replace(',','')) or amount[2] != 'USD':
        raise RuntimeError('Incomplete/conflicting PayPal items for '+invoice)
    return dict(id=invoice,email=buyer[2].strip(),name=buyer[1].strip(),
                date=field('Transaction date'),order_date=datetime.strptime(field('Transaction date'),'%b %d, %Y').date().isoformat(),
                transaction=field('Transaction ID'),total=amount[1].replace(',',''),currency=amount[2],
                instructions=field('Instructions to merchant'),items=items,message=mid)


def fetch(gmail, query):
    ids=[];page=None;pages=set()
    while True:
        args=dict(userId='me',q=query,maxResults=500,includeSpamTrash=True)
        if page:args['pageToken']=page
        result=gmail.users().messages().list(**args).execute(num_retries=2)
        ids.extend(item['id'] for item in result.get('messages',[]))
        page=result.get('nextPageToken')
        if not page:break
        if page in pages:raise RuntimeError('Repeated PayPal Gmail pagination token')
        pages.add(page)
    payments={}
    for mid in dict.fromkeys(ids):
        meta=gmail.users().messages().get(userId='me',id=mid,format='metadata',metadataHeaders=['Subject']).execute(num_retries=2)
        subject=next((h['value'] for h in meta.get('payload',{}).get('headers',[]) if h['name'].lower()=='subject'),'')
        if subject.strip()!='Notification of payment received':continue
        message=gmail.users().messages().get(userId='me',id=mid,format='raw').execute(num_retries=2)
        p=parse(mid,message['internalDate'],base64.urlsafe_b64decode(message['raw']+'==='))
        if p['id'] in payments:
            previous=payments[p['id']]
            # R-number is the join; distinct transactions are not silently collapsed.
            if any(previous[k]!=p[k] for k in p if k!='message'):
                raise RuntimeError('Conflicting PayPal payments for '+p['id'])
        else:payments[p['id']]=p
    return payments


def provisional_identity(row):
    return bool('PayPal-only;' in str(row[62]) or (row[49] and not row[3]))


def values(payment, item, row):
    notes=[]
    if provisional_identity(row):notes.append('PayPal-only; reservation identity unavailable')
    elif str(row[3]).casefold()!=payment['email'].casefold():notes.append('Payer email differs from reservation email')
    customer=row[27] or row[19]
    if customer and ' '.join(str(customer).split()).casefold()!=' '.join(payment['name'].split()).casefold():
        notes.append('Payer name differs from reservation customer name')
    if row[41]!=item['sku']:notes.append('PayPal item date differs from current reservation SKU')
    payment_date=datetime.strptime(payment['date'],'%b %d, %Y').date()
    if isinstance(row[4],(int,float)) and (datetime(1899,12,30)+timedelta(days=row[4])).date()!=payment_date:
        notes.append('PayPal payment date differs from order date')
    if row[6] not in ('','Paid'):
        notes.append('Recorded payment status differs from PayPal payment receipt')
    return [payment['email'],payment['name'],payment['date'],payment['transaction'],payment['total'],payment['currency'],item['title'],item['item_id'],item['qty'],item['unit'],item['total'],payment['instructions'],'https://mail.google.com/mail/u/0/#all/'+payment['message'],'; '.join(notes)]
