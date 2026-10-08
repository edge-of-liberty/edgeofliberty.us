"""Both-source importer tests; Gmail, Sheets and writes are entirely in memory."""
import copy
from email.message import EmailMessage
import unittest
from unittest.mock import MagicMock, patch
import import_gmail_orders as imp
import paypal_orders as paypal
from test_import_gmail_orders import ImportTests


def payment(oid='R123',skus=('261018',)):
    items=[dict(sku=sku,title='Edge of Liberty Craft Fair '+{'261018':'Oct 18, 2026','261101':'Nov 01, 2026'}[sku],item_id='uuid-'+sku,unit='20.00',qty='1',total='20.00') for sku in skus]
    return dict(id=oid,email='payer@example.invalid',name='Different Payer',date='Oct 7, 2026',order_date='2026-10-07',transaction='TX1',total=str(20*len(items))+'.00',currency='USD',instructions="The buyer hasn't entered any instructions.",items=items,message='paypal-message')


def godaddy(oid='R123',sku='261018'):
    r=ImportTests().row(sku=sku);r[0]=oid;r[6]=payment(skus=(sku,))['items'][0]['title'];r[13]='Business';return r


class MemorySheets:
    def __init__(self):
        header=['']*63;header[2]='Order #';header[49:63]=paypal.HEADERS
        old=['']*63;old[0:3]=['=key','=lookup','R0']
        self.rows=[header,old];self.calls=0;self.fail=False
        self.api=MagicMock()
        self.api.spreadsheets().get().execute.side_effect=self.get
        self.api.spreadsheets().values().get().execute.side_effect=self.read
        self.api.spreadsheets().batchUpdate().execute.side_effect=self.write
    def get(self,**kw):
        args=self.api.spreadsheets().get.call_args.kwargs
        if args['fields']=='sheets(properties)':
            return {'sheets':[{'properties':{'sheetId':123,'title':'DOWNLOAD orders','gridProperties':{'rowCount':10,'columnCount':63}}}]}
        return {'sheets':[{'data':[{'rowData':[{'values':[{'userEnteredValue':{'numberValue':v} if isinstance(v,(int,float)) else {'formulaValue':v} if str(v).startswith('=') else {'stringValue':v}} if v!='' else {} for v in row]} for row in self.rows]}]}]}
    def read(self,**kw):
        args=self.api.spreadsheets().values().get.call_args.kwargs
        if 'Craft Fair Planning' in args['range']:return {'values':[]}
        if args['range']=="'DOWNLOAD orders'!A:D":
            return {'values':[[r[0],25 if r[3] else '#N/A',r[2],r[3]] for r in self.rows]}
        return {'values':copy.deepcopy(self.rows)}
    def write(self,**kw):
        self.calls+=1
        args=self.api.spreadsheets().batchUpdate.call_args.kwargs
        for req in args['body']['requests']:
            if 'copyPaste' in req:
                dest=req['copyPaste']['destination']
                while len(self.rows)<dest['endRowIndex']:self.rows.append(['']*63)
                for i in range(dest['startRowIndex'],dest['endRowIndex']):self.rows[i][:2]=['=key','=lookup']
            if 'updateCells' in req:
                u=req['updateCells'];i=u['start']['rowIndex'];c=u['start']['columnIndex']
                while len(self.rows)<=i:self.rows.append(['']*63)
                self.rows[i][c]=next(iter(u['rows'][0]['values'][0]['userEnteredValue'].values()))
        if self.fail:raise OSError('uncertain write')


class CombinedTests(unittest.TestCase):
    def run_import(self,sheet,primary,payments,dry=False):
        gmail=MagicMock();gmail.users().getProfile().execute.return_value={'emailAddress':'admin@batshitcrazyfarms.com'}
        receipt=[]
        with patch('order_email_review.clients',return_value=(gmail,sheet.api)),patch('google_sheets.load_config',return_value={'spreadsheet_id':'test','orders_sheet_id':123}),patch.object(imp,'fetch_rows',return_value=([],primary)),patch.object(paypal,'fetch',return_value=payments),patch('builtins.print'):
            imp.process(dry,report=receipt.append)
        return receipt
    def test_shifted_paypal_mapping_preserves_instructions(self):
        s=MemorySheets()
        self.run_import(s,[godaddy()],{})
        s.rows[2][48]='Keep these instructions'
        self.run_import(s,[],{'R123':payment()})
        self.assertEqual(s.rows[2][48],'Keep these instructions')
        self.assertEqual(s.rows[2][49],'payer@example.invalid')
        self.assertEqual(s.rows[2][52],'TX1')
        self.assertIn('Payer email differs',s.rows[2][62])
        self.assertTrue(all('BL' not in call.kwargs.get('range','')
                            for call in s.api.spreadsheets().values().get.call_args_list))
    def test_old_paypal_header_layout_stops_before_write(self):
        s=MemorySheets();s.rows[0][49:63]=['']+paypal.HEADERS[:-1]
        with self.assertRaisesRegex(RuntimeError,'headers AX:BK differ'):
            self.run_import(s,[],{})
        self.assertEqual(s.calls,0)
    def test_both_sources_and_repeat_scan(self):
        s=MemorySheets();p=payment();r=godaddy()
        receipt=self.run_import(s,[r],{'R123':p})
        self.assertEqual(receipt[-1]['orders'][0]['id'],'R123')
        self.assertEqual(s.rows[2][3],'a@example.invalid')
        self.assertEqual(s.rows[2][49],'payer@example.invalid')
        self.assertIn('Payer email differs',s.rows[2][62])
        self.assertEqual(s.calls,1)
        self.run_import(s,[r],{'R123':p})
        self.assertEqual(s.calls,1)
        self.assertEqual(len(s.rows),3)
    def test_paypal_first_then_godaddy_fills_same_row(self):
        s=MemorySheets();p=payment()
        receipt=self.run_import(s,[],{'R123':p})
        self.assertEqual(s.rows[2][3],'payer@example.invalid')
        self.assertEqual(s.rows[2][41],'261018')
        self.assertTrue(any('identity missing' in w for w in receipt[-1]['warnings']))
        self.run_import(s,[godaddy()],{'R123':p})
        self.assertEqual(len(s.rows),3)
        self.assertEqual(s.rows[2][3],'a@example.invalid')
        self.assertEqual(s.rows[2][27],'Example')
        self.assertEqual(s.rows[2][4],imp.sheets_date(godaddy()[2]))
        self.assertNotIn('PayPal-only',s.rows[2][62])
    def test_same_email_godaddy_arrival_clears_provisional_without_duplicate(self):
        s=MemorySheets();p=payment()
        self.run_import(s,[],{'R123':p})
        r=godaddy();r[1]=p['email']
        self.run_import(s,[r],{'R123':p})
        self.assertEqual(len(s.rows),3)
        self.assertEqual(s.rows[2][3],p['email'])
        self.assertNotIn('PayPal-only',s.rows[2][62])
        calls=s.calls
        self.run_import(s,[r],{'R123':p})
        self.assertEqual(s.calls,calls)
    def test_delayed_godaddy_completes_even_without_paypal_in_scan(self):
        s=MemorySheets();self.run_import(s,[],{'R123':payment()})
        self.run_import(s,[godaddy()],{})
        self.assertEqual(s.rows[2][3],'a@example.invalid')
        self.assertNotIn('PayPal-only',s.rows[2][62])
        self.assertEqual(len(s.rows),3)
    def test_repeated_paypal_only_scan_keeps_provisional_identity(self):
        s=MemorySheets();p=payment()
        self.run_import(s,[],{'R123':p});calls=s.calls
        receipt=self.run_import(s,[],{'R123':p})
        self.assertEqual(s.calls,calls)
        self.assertEqual(s.rows[2][3],p['email'])
        self.assertTrue(any('identity missing' in w for w in receipt[-1]['warnings']))
    def test_godaddy_first_then_paypal_enriches(self):
        s=MemorySheets()
        self.run_import(s,[godaddy()],{})
        base=s.rows[2][:49]
        self.run_import(s,[godaddy()],{'R123':payment()})
        self.assertEqual(s.rows[2][:49],base)
        self.assertEqual(s.rows[2][52],'TX1')
        self.assertEqual(len(s.rows),3)
    def test_multiline_different_source_order(self):
        s=MemorySheets();p=payment(skus=('261101','261018'))
        self.run_import(s,[godaddy(sku='261018'),godaddy(sku='261101')],{'R123':p})
        self.assertEqual(len(s.rows),4)
        self.assertEqual({r[41] for r in s.rows[2:]},{'261018','261101'})
        self.assertEqual({r[55] for r in s.rows[2:]},{i['title'] for i in p['items']})
    def test_manual_product_fulfillment_and_payment_preserved(self):
        s=MemorySheets();self.run_import(s,[godaddy()],{})
        s.rows[2][41]='261101';s.rows[2][5]='Fulfilled';s.rows[2][6]='Refunded'
        self.run_import(s,[],{'R123':payment()})
        self.assertEqual(s.rows[2][41],'261101')
        self.assertEqual(s.rows[2][5:7],['Fulfilled','Refunded'])
        self.assertIn('item date differs',s.rows[2][62])
    def test_new_product_conflict_stops_before_write(self):
        s=MemorySheets()
        with self.assertRaises(RuntimeError):self.run_import(s,[godaddy()],{'R123':payment(skus=('261101',))})
        self.assertEqual(s.calls,0)
    def test_new_amount_conflict_stops_before_write(self):
        s=MemorySheets();r=godaddy();r[10]='40.00'
        with self.assertRaises(RuntimeError):self.run_import(s,[r],{'R123':payment()})
        self.assertEqual(s.calls,0)
    def test_multiple_transactions_never_overwrite(self):
        s=MemorySheets();self.run_import(s,[godaddy()],{'R123':payment()})
        p=payment();p['transaction']='OTHER'
        with self.assertRaises(RuntimeError):self.run_import(s,[],{'R123':p})
        self.assertEqual(s.calls,1)
    def test_dry_run_and_empty_scan_do_not_write(self):
        s=MemorySheets();self.run_import(s,[godaddy()],{'R123':payment()},True)
        self.assertEqual(s.calls,0)
        receipt=self.run_import(s,[],{})
        self.assertEqual(receipt[-1]['warnings'],[])
        self.assertEqual(s.calls,0)
    def test_malformed_godaddy_stops_before_write(self):
        s=MemorySheets();r=godaddy();r[16]='Malformed'
        with self.assertRaises(RuntimeError):self.run_import(s,[r],{})
        self.assertEqual(s.calls,0)
    def test_uncertain_write_is_not_retried(self):
        s=MemorySheets();s.fail=True
        with self.assertRaises(OSError):self.run_import(s,[],{'R123':payment()})
        self.assertEqual(s.calls,1)


class PayPalFetchTests(unittest.TestCase):
    def test_exact_subject_filter_and_identical_duplicate_collapse(self):
        import base64
        g=MagicMock()
        g.users().messages().list().execute.return_value={'messages':[{'id':'one'},{'id':'forward'},{'id':'two'}]}
        raw=base64.urlsafe_b64encode(PayPalParserTests().raw()).decode()
        original={'payload':{'headers':[{'name':'Subject','value':'Notification of payment received'}]}}
        forward={'payload':{'headers':[{'name':'Subject','value':'Fwd: Notification of payment received'}]}}
        g.users().messages().get().execute.side_effect=[original,{'raw':raw,'internalDate':'1791417600000'},forward,original,{'raw':raw,'internalDate':'1791417600000'}]
        self.assertEqual(list(paypal.fetch(g,'query')),['R123'])
    def test_different_transactions_same_invoice_stop(self):
        import base64
        g=MagicMock();g.users().messages().list().execute.return_value={'messages':[{'id':'one'},{'id':'two'}]}
        raw=PayPalParserTests().raw()
        meta={'payload':{'headers':[{'name':'Subject','value':'Notification of payment received'}]}}
        g.users().messages().get().execute.side_effect=[meta,{'raw':base64.urlsafe_b64encode(raw).decode(),'internalDate':'1791417600000'},meta,{'raw':base64.urlsafe_b64encode(raw.replace(b'TX1',b'TX2')).decode(),'internalDate':'1791417600000'}]
        with self.assertRaises(RuntimeError):paypal.fetch(g,'query')


class PayPalParserTests(unittest.TestCase):
    def raw(self,invoice='R123',title='Edge of Liberty Craft Fair Oct 18, 2026'):
        m=EmailMessage();m['Subject']='Notification of payment received'
        m.set_content('You received a payment of $20.00 USD from Payer\nTransaction ID\nTX1\nTransaction date\nOct 7, 2026\nBuyer\nDifferent Payer\npayer@example.invalid\nInvoice ID\n'+invoice+'\nDescription\n'+title+'\nItem# uuid\n$20.00 USD\n1\n$20.00 USD\nInstructions to merchant\nNone\nPayment sent to paypal@batshitcrazyfarms.com')
        return m.as_bytes()
    def test_known_product_invoice_and_identity(self):
        p=paypal.parse('mid','1791417600000',self.raw())
        self.assertEqual(p['id'],'R123');self.assertEqual(p['items'][0]['sku'],'261018')
        self.assertEqual(p['email'],'payer@example.invalid')
    def test_unknown_invoice_product_and_amount_rejected(self):
        for raw in [self.raw(invoice='unknown'),self.raw(title='Unknown Product'),self.raw().replace(b'1\n$20.00',b'2\n$20.00')]:
            with self.assertRaises(RuntimeError):paypal.parse('mid','1791417600000',raw)

if __name__=='__main__':unittest.main()
