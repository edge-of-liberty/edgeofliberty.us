import unittest
from unittest.mock import patch, MagicMock
import import_gmail_orders as imp

class ImportTests(unittest.TestCase):
 def row(self,sku='261004',message='m'):
  r=['']*24
  for i,v in {0:'R123',1:'a@example.invalid',2:'2026-09-11',3:'Paid',4:'Example',5:'+15555555555',7:sku,8:'1',17:message}.items():r[i]=v
  return r
 def test_order_dedupe_keeps_multi_item(self):
  rows=[self.row(),self.row('261018'),self.row('261101')]
  with patch.object(imp,'fetch_rows',return_value=([],rows)):
   self.assertEqual(len(imp.prepare(None,set())),3)
   self.assertEqual(imp.prepare(None,{'R123'}),[])
 def test_duplicate_messages_collapse(self):
  with patch.object(imp,'fetch_rows',return_value=([],[self.row(),self.row(message='m2')])):
   self.assertEqual(len(imp.prepare(None,set())),1)
 def test_conflicting_duplicates_stop(self):
  with patch.object(imp,'fetch_rows',return_value=([],[self.row(),self.row('261101','m2')])):
   with self.assertRaises(RuntimeError):imp.prepare(None,set())
 def test_write_boundary_and_color_order(self):
  rr=imp.requests_for([self.row()],123,217,233)
  self.assertEqual(rr[0]['copyPaste']['pasteType'],'PASTE_FORMULA')
  self.assertEqual(rr[0]['copyPaste']['destination']['startRowIndex'],217)
  self.assertEqual([x['updateCells']['start']['columnIndex'] for x in rr if 'updateCells' in x],[2,26,41])
  self.assertEqual(rr[-1]['repeatCell']['cell']['userEnteredFormat']['backgroundColor'],imp.COLOR)
  self.assertEqual(rr[-1]['repeatCell']['range']['endColumnIndex'],42)

if __name__=='__main__':unittest.main()

class DailyCommandTests(unittest.TestCase):
 row = ImportTests.row
 def test_missing_vendor_message(self):
  r=self.row();r[13]='Hazy Blaze Tie-Dye';r[1]='hazyblazetiedye@gmail.com';r[0]='R839479769658'
  self.assertEqual(imp.missing_vendor_messages([r], [['key','#N/A']]),[
   'NEW VENDOR NEEDS SETUP: Hazy Blaze Tie-Dye — hazyblazetiedye@gmail.com — R839479769658 — 261004 — Paid'])
  self.assertEqual(imp.missing_vendor_messages([r], [['key',25]]),[])
 def test_summary_counts_no_fixed_september_cutoff(self):
  old=self.row();old[2]='2026-08-31';old[0]='R9'
  new=self.row();new[0]='R456'
  stats={}
  with patch.object(imp,'fetch_rows',return_value=([],[self.row(),old,new])):
   rows=imp.prepare(None,{'R123'},stats=stats)
  self.assertEqual(stats,{'checked':3,'skipped':1})
  self.assertEqual([r[0] for r in rows],['R9','R456'])
 def test_cli_dry_run(self):
  with patch('sys.argv',['import_gmail_orders.py','--dry-run']),patch.object(imp,'process') as process:
   imp.main()
  process.assert_called_once_with(True)

 def test_pending_order_dry_run_never_writes(self):
  gmail, sheets = MagicMock(), MagicMock()
  gmail.users().getProfile().execute.return_value = {'emailAddress':'admin@batshitcrazyfarms.com'}
  sheets.spreadsheets().get().execute.return_value = {'sheets':[{'properties':{'sheetId':123,'title':'DOWNLOAD orders','gridProperties':{'rowCount':233}}}]}
  sheets.spreadsheets().values().get().execute.return_value = {'values':[['header']]}
  def prepared(g, existing, stats, query):
   stats.update(checked=1,skipped=0)
   return [self.row()]
  with patch('order_email_review.clients',return_value=(gmail,sheets)), patch('google_sheets.load_config',return_value={'spreadsheet_id':'test','orders_sheet_id':123}), patch.object(imp,'prepare',side_effect=prepared):
   imp.process(dry_run=True)
  sheets.spreadsheets().batchUpdate.assert_not_called()

 def test_dynamic_45_day_query(self):
  from datetime import datetime, timedelta
  from zoneinfo import ZoneInfo
  now=datetime(2026,9,26,12,0,tzinfo=ZoneInfo('America/Chicago'))
  query,start,end=imp.lookback(now)
  self.assertEqual(start,now-timedelta(days=45))
  self.assertEqual(end,now)
  self.assertEqual(query,f'subject:"New Order" after:{int(start.timestamp())-1} before:{int(now.timestamp())+1}')
  later=imp.lookback(now+timedelta(days=2))
  self.assertEqual(later[1],start+timedelta(days=2))

 def test_optional_phone_and_numeric_date(self):
  r=self.row();r[5]=''
  with patch.object(imp,'fetch_rows',return_value=([],[r])):
   self.assertEqual(len(imp.prepare(None,set())),1)
  requests=imp.requests_for([r],123,227,240,'m/d/yyyy')
  updates=[x['updateCells'] for x in requests if 'updateCells' in x]
  value=updates[0]['rows'][0]['values'][2]['userEnteredValue']
  self.assertEqual(value,{'numberValue':46276})
  self.assertEqual(updates[1]['rows'][0]['values'][0]['userEnteredValue'],{'stringValue':''})
  fmt=requests[-2]['repeatCell']
  self.assertEqual(fmt['range']['startRowIndex'],227)
  self.assertEqual(fmt['cell']['userEnteredFormat']['numberFormat'],{'type':'DATE','pattern':'m/d/yyyy'})
 def test_invalid_date_blocks_before_write(self):
  r=self.row();r[2]='2026-02-30'
  with patch.object(imp,'fetch_rows',return_value=([],[r])):
   with self.assertRaises(ValueError):imp.prepare(None,set())
