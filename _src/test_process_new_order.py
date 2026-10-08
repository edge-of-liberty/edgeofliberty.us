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
    def exercise(self,status='complete',orders=None,code=0,build_fail=False,warnings=None):
        receipt={'status':status,'orders':[] if orders is None else orders,'warnings':warnings or []}
        with patch.object(w,'check_repositories') as check,patch.object(w,'read_result',return_value=receipt),\
             patch.object(w,'run_logged') as run:
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
            self.assertEqual(check.call_count,2)
            self.assertEqual(sum(c.args[0][0]=='./_src/process_orders.sh' for c in run.call_args_list),1)
    def test_attention_warnings_still_build(self):
        warning='⚠ Order R123 has an unresolved Column B lookup (#N/A)'
        with patch('builtins.print') as output:
            self.exercise(warnings=[warning])
        self.assertIn(warning, output.call_args.args[0])
        self.assertIn('Site refreshed and published', output.call_args.args[0])
    def test_setup_receipt_keeps_attention_warning(self):
        result={'status':'needs_vendor_setup','orders':[ORDER],'warnings':['⚠ Example: Planning Column F sitemap/setup unresolved']}
        self.assertIn('Planning Column F',w.order_outcome(result,0))
    def test_enrichment_receipt_reports_update(self):
        self.assertEqual(w.imported_label({'orders':[],'updated_orders':['R123']}),'Order details updated: R123')
    def test_zero_imports_still_builds(self):self.exercise()
    def test_one_import_builds(self):self.exercise(orders=[ORDER])
    def test_multiple_imports_build_once(self):self.exercise(orders=[ORDER,{**ORDER,'id':'R456'}])
    def test_unrecognized_before_write_still_builds(self):self.exercise('before_write',code=1)
    def test_uncertain_write_still_builds(self):self.exercise('write_attempted',code=1)
    def test_unmatched_vendor_still_builds(self):self.exercise('needs_vendor_setup',[{**ORDER,'needs_vendor_setup':True}])
    def test_incomplete_receipt_still_builds(self):self.exercise('write_attempted')
    def test_build_failure_retains_import(self):self.exercise(orders=[ORDER],build_fail=True)
    def test_dirty_repo_never_imports(self):
        with patch.object(w,'check_repositories',side_effect=w.Stop('dirty')),patch.object(w,'run_logged') as run:
            with self.assertRaises(w.Stop):w.run()
            run.assert_not_called()
    def test_missing_receipt_still_builds(self):
        with patch.object(w,'check_repositories'),patch.object(w,'read_result',side_effect=w.Stop('missing')),patch.object(w,'run_logged',return_value=SimpleNamespace(returncode=0)) as run:
            w.run()
            self.assertEqual(run.call_args.args[0],['./_src/build.sh','all'])
            self.assertEqual(run.call_count,2)
    def test_invalid_missing_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'result.json'
            with self.assertRaises(w.Stop):w.read_result(p)
            p.write_text('{}')
            with self.assertRaises(w.Stop):w.read_result(p)
if __name__=='__main__':unittest.main()
