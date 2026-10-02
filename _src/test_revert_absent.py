"""Offline tests; all Sheets and production operations are mocked."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
import revert_absent as r

TARGET={'slug':'example','name':'Example','date':'2026-10-04','event':'october-04-2026','row':9,'column':4}
FORMULA={'formulaValue':'=VLOOKUP(A10,Orders!A:B,2,FALSE)'}
CONFIG={'year':2026,'planning_sheet_id':123,'spreadsheet_id':'test'}

class AuditTests(unittest.TestCase):
    def save(self,root,name,before=FORMULA,target=TARGET,verified=True,time='2026-10-02T10:00:00+00:00'):
        records=[{'phase':'before','time':time,'target':target,'before':before}]
        if verified:records.append({'phase':'verified','target':target})
        (root/name).write_text(json.dumps(records))
    def test_original_formula_skips_idempotent_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);self.save(p,'a.json');self.save(p,'b.json',{'stringValue':'Absent'},time='2026-10-03')
            self.assertEqual(r.original_formula(TARGET,p),FORMULA)
    def test_missing_unverified_or_nonformula_audit_stops(self):
        for mode in ('missing','unverified','literal'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                p=Path(temp)
                if mode=='unverified':self.save(p,'a.json',verified=False)
                if mode=='literal':self.save(p,'a.json',{'stringValue':'Paid'})
                with self.assertRaises(r.Stop):r.original_formula(TARGET,p)
    def test_moved_row_stops_no_formula_translation(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);self.save(p,'a.json',target={**TARGET,'row':10})
            with self.assertRaises(r.Stop):r.original_formula(TARGET,p)

class RestoreTests(unittest.TestCase):
    def invoke(self,before,after=FORMULA,changed=False):
        api=MagicMock();audit=MagicMock()
        with patch.object(r,'snapshot'),patch.object(r,'resolve',return_value=TARGET),patch.object(r,'original_formula',return_value=FORMULA),patch.object(r,'entered',side_effect=[before,{} if changed else before,after]):
            target=r.restore(api,CONFIG,'Example','Oct 4',audit)
        return api,target
    def test_exact_one_cell_formula_write(self):
        api,target=self.invoke({'stringValue':'Absent'})
        request=api.spreadsheets().batchUpdate.call_args.kwargs['body']['requests']
        self.assertEqual(request,[{'updateCells':{'range':{'sheetId':123,'startRowIndex':9,'endRowIndex':10,'startColumnIndex':4,'endColumnIndex':5},'rows':[{'values':[{'userEnteredValue':FORMULA}]}],'fields':'userEnteredValue'}}])
    def test_already_restored_no_write(self):
        api,_=self.invoke(FORMULA);api.spreadsheets().batchUpdate.assert_not_called()
    def test_unrelated_status_not_overwritten(self):
        with self.assertRaises(r.Stop):self.invoke({'stringValue':'Paid'})
    def test_changed_cell_stops(self):
        with self.assertRaises(r.Stop):self.invoke({'stringValue':'Absent'},changed=True)
    def test_formula_readback_required(self):
        with self.assertRaises(r.Stop):self.invoke({'stringValue':'Absent'},after={'stringValue':'Paid'})
    def test_production_failure_retains_formula(self):
        with patch.object(r,'check_repositories'),patch.object(r,'load_config'),patch.object(r,'service'),patch.object(r,'private_write'),patch.object(r,'restore',return_value=TARGET) as restore,patch.object(r,'run_logged',side_effect=RuntimeError('build failed')):
            with self.assertRaisesRegex(r.Stop,'Formula retained'):r.run('Example','Oct 4')
            restore.assert_called_once()
    def test_success_ends_at_production_completion(self):
        with patch.object(r,'check_repositories') as pre,patch.object(r,'load_config'),patch.object(r,'service'),patch.object(r,'private_write'),patch.object(r,'restore',return_value=TARGET),patch.object(r,'run_logged') as run:
            r.run('Example','Oct 4')
            self.assertIn('./_src/process_orders.sh && ./_src/build.sh all',run.call_args.args[0])
            self.assertEqual(pre.call_count,1)
            run.assert_called_once()

class BelowTests(unittest.TestCase):
    def test_relative_absolute_and_quoted_references(self):
        original={'formulaValue':'=IFERROR(VLOOKUP($A11,Orders!$A$2:$B$99,2,FALSE),"A11")'}
        with patch.object(r,'entered',return_value=original):
            formula,source,_=r.formula_from_below(None,CONFIG,TARGET)
        self.assertEqual(source['row'],10)
        self.assertEqual(formula['formulaValue'],'=IFERROR(VLOOKUP($A10,Orders!$A$2:$B$99,2,FALSE),"A11")')
    def test_invalid_source_stops(self):
        for value in [{'stringValue':'Absent'},{'formulaValue':'=VLOOKUP($A$11,Orders!A:B,2,FALSE)'},{'formulaValue':'=VLOOKUP(INDIRECT("A11"),A:B,2,FALSE)'}]:
            with patch.object(r,'entered',return_value=value),self.assertRaises(r.Stop):
                r.formula_from_below(None,CONFIG,TARGET)
    def test_only_target_written_source_preserved(self):
        api=MagicMock();below={'formulaValue':'=VLOOKUP(A11,Orders!A:B,2,FALSE)'}
        values=[below,{'stringValue':'Absent'},{'stringValue':'Absent'},below,FORMULA,below]
        with patch.object(r,'snapshot'),patch.object(r,'resolve',return_value=TARGET),patch.object(r,'entered',side_effect=values):
            r.restore(api,CONFIG,'Example','Oct 4',MagicMock(),from_below=True)
        req=api.spreadsheets().batchUpdate.call_args.kwargs['body']['requests']
        self.assertEqual(len(req),1)
        self.assertEqual(req[0]['updateCells']['range']['startRowIndex'],9)
        self.assertEqual(req[0]['updateCells']['rows'][0]['values'][0]['userEnteredValue'],FORMULA)

if __name__=='__main__':unittest.main()
