"""Offline workflow tests: external processes, services and publication are mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import process_new_order as w
import import_gmail_orders as imp

ORDER={'id':'R123','skus':['261004'],'needs_vendor_setup':False}

class WorkflowTests(unittest.TestCase):
    def exercise(self,status='complete',orders=None,code=0,build_fail=False):
        receipt={'status':status,'orders':[] if orders is None else orders}
        with patch.object(w,'check_repositories') as check,patch.object(w,'read_result',return_value=receipt),\
             patch.object(w.subprocess,'run') as run,patch.object(w,'verify_publication') as verify:
            def response(args,**kwargs):
                if args[0]=='./_src/process_orders.sh':return SimpleNamespace(returncode=code)
                if build_fail:raise w.subprocess.CalledProcessError(1,args)
                return SimpleNamespace(returncode=0)
            run.side_effect=response
            success=not build_fail
            if success:w.run()
            else:
                with self.assertRaises(w.Stop) as exc:w.run()
                message=str(exc.exception)
                if status in ('write_attempted','needs_vendor_setup') or build_fail:
                    self.assertNotIn('No changes made',message)
            builds=[c for c in run.call_args_list if c.args[0]==['./_src/build.sh','all']]
            self.assertEqual(len(builds),1)
            self.assertEqual(verify.call_count,int(success))
            self.assertEqual(sum(c.args[0][0]=='./_src/process_orders.sh' for c in run.call_args_list),1)
    def test_zero_imports_still_builds(self):self.exercise()
    def test_one_import_builds(self):self.exercise(orders=[ORDER])
    def test_multiple_imports_build_once(self):self.exercise(orders=[ORDER,{**ORDER,'id':'R456'}])
    def test_unrecognized_before_write_still_builds(self):self.exercise('before_write',code=1)
    def test_uncertain_write_still_builds(self):self.exercise('write_attempted',code=1)
    def test_unmatched_vendor_still_builds(self):self.exercise('needs_vendor_setup',[{**ORDER,'needs_vendor_setup':True}])
    def test_incomplete_receipt_still_builds(self):self.exercise('write_attempted')
    def test_build_failure_retains_import(self):self.exercise(orders=[ORDER],build_fail=True)
    def test_dirty_repo_never_imports(self):
        with patch.object(w,'check_repositories',side_effect=w.Stop('dirty')),patch.object(w.subprocess,'run') as run:
            with self.assertRaises(w.Stop):w.run()
            run.assert_not_called()
    def test_missing_receipt_still_builds(self):
        with patch.object(w,'check_repositories'),patch.object(w,'read_result',side_effect=w.Stop('missing')),patch.object(w.subprocess,'run',return_value=SimpleNamespace(returncode=1)) as run,patch.object(w,'verify_publication') as verify:
            w.run()
            self.assertEqual(run.call_args.args[0],['./_src/build.sh','all'])
            verify.assert_called_once()
    def test_unrecognized_order_no_sheet_write_but_refresh_completes(self):
        gmail,sheets=MagicMock(),MagicMock()
        gmail.users().getProfile().execute.return_value={'emailAddress':'admin@batshitcrazyfarms.com'}
        sheets.spreadsheets().get().execute.return_value={'sheets':[{'properties':{'sheetId':123,'title':'DOWNLOAD orders','gridProperties':{'rowCount':10}}}]}
        sheets.spreadsheets().values().get().execute.return_value={'values':[['header']]}
        from test_import_gmail_orders import ImportTests
        bad=ImportTests().row();bad[16]='No recognizable SKU line items'
        receipt={}
        def report(value):receipt.update(value)
        def process(args,**kwargs):
            if args[0]=='./_src/build.sh':return SimpleNamespace(returncode=0)
            try:imp.process(report=report)
            except RuntimeError:return SimpleNamespace(returncode=1)
            self.fail('Malformed order must be rejected')
        with patch('order_email_review.clients',return_value=(gmail,sheets)),patch('google_sheets.load_config',return_value={'spreadsheet_id':'test','orders_sheet_id':123}),patch.object(imp,'fetch_rows',return_value=([],[bad])),patch.object(w,'check_repositories'),patch.object(w,'read_result',side_effect=lambda p:receipt),patch.object(w.subprocess,'run',side_effect=process) as run,patch.object(w,'verify_publication') as verify:
            w.run()
            sheets.spreadsheets().batchUpdate.assert_not_called()
            self.assertEqual(run.call_args.args[0],['./_src/build.sh','all'])
            verify.assert_called_once()

    def test_invalid_missing_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'result.json'
            with self.assertRaises(w.Stop):w.read_result(p)
            p.write_text('{}')
            with self.assertRaises(w.Stop):w.read_result(p)
    def test_stale_live_page_never_success(self):
        with patch.object(w,'publication_targets',return_value=[('url',['new'])]),patch.object(w,'matches_live',return_value=False),patch.object(w.time,'sleep'):
            with self.assertRaises(w.Stop):w.verify_publication()
    def test_generated_targets_include_next_fair_and_history(self):
        targets=w.publication_targets()
        self.assertTrue(any(url.endswith('/craft-fair/') and all('https://' in chunk for chunk in chunks) for url,chunks in targets))
        self.assertTrue(any('/may-17-2026/' in url for url,_ in targets))
        self.assertTrue(any('/october-18-2026/' in url for url,_ in targets))

class ReceiptTests(unittest.TestCase):
    def test_zero_import_receipt_no_write(self):
        gmail,sheets=MagicMock(),MagicMock()
        gmail.users().getProfile().execute.return_value={'emailAddress':'admin@batshitcrazyfarms.com'}
        sheets.spreadsheets().get().execute.return_value={'sheets':[{'properties':{'sheetId':123,'title':'DOWNLOAD orders','gridProperties':{'rowCount':10}}}]}
        sheets.spreadsheets().values().get().execute.return_value={'values':[['header']]}
        def prepared(g,existing,stats,query):stats.update(checked=0,skipped=0);return []
        report=MagicMock()
        with patch('order_email_review.clients',return_value=(gmail,sheets)),patch('google_sheets.load_config',return_value={'spreadsheet_id':'test','orders_sheet_id':123}),patch.object(imp,'prepare',side_effect=prepared):
            imp.process(report=report)
        self.assertEqual([c.args[0]['status'] for c in report.call_args_list],['before_write','complete'])
        sheets.spreadsheets().batchUpdate.assert_not_called()
    def test_verified_import_receipt_and_missing_vendor_branch(self):
        from test_import_gmail_orders import ImportTests
        for lookup, expected_status in [(25, 'complete'), ('#N/A', 'needs_vendor_setup')]:
            with self.subTest(lookup=lookup):
                gmail,sheets=MagicMock(),MagicMock()
                gmail.users().getProfile().execute.return_value={'emailAddress':'admin@batshitcrazyfarms.com'}
                row=ImportTests().row()
                before=[['=key','=lookup','R0']]
                actual=['']*50
                for k,val in {0:'=key',1:'=lookup',2:row[0],3:row[1],4:imp.sheets_date(row[2]),
                              6:row[3],26:row[5],27:row[4],41:row[7]}.items():actual[k]=val
                sheets.spreadsheets().values().get().execute.side_effect=[
                    {'values':before},{'values':before},{'values':before+[actual]},
                    {'values':[[row[7]+row[1],lookup]]}]
                meta={'sheets':[{'properties':{'sheetId':123,'title':'DOWNLOAD orders','gridProperties':{'rowCount':10}}}]}
                color={'sheets':[{'data':[{'rowData':[{'values':[{'userEnteredFormat':{'backgroundColor':imp.COLOR}} for _ in range(42)]}]}]}]}
                # Existing code expects a sheet entry for the optional date format.
                sheets.spreadsheets().get().execute.side_effect=[meta,meta,{}, {'sheets':[{}]}, {},color]
                def prepared(g,existing,stats,query):stats.update(checked=1,skipped=0);return [row]
                report=MagicMock()
                with patch('order_email_review.clients',return_value=(gmail,sheets)),patch('google_sheets.load_config',return_value={'spreadsheet_id':'test','orders_sheet_id':123}),patch.object(imp,'prepare',side_effect=prepared):
                    imp.process(report=report)
                self.assertEqual([c.args[0]['status'] for c in report.call_args_list],['before_write','write_attempted',expected_status])
                self.assertEqual(report.call_args.args[0]['orders'][0]['id'],'R123')
                sheets.spreadsheets().batchUpdate.assert_called_once()

    def test_unsafe_batch_does_not_partially_import(self):
        from test_import_gmail_orders import ImportTests
        good=ImportTests().row();bad=good[:];bad[0]='R456';bad[16]='Unrecognized SKU line items'
        with patch.object(imp,'fetch_rows',return_value=([],[good,bad])):
            with self.assertRaises(RuntimeError):imp.prepare(None,set())

if __name__=='__main__':unittest.main()
