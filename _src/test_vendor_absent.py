"""Offline only: no credentials, spreadsheet writes, production build, or publication."""
import unittest
from unittest.mock import MagicMock, patch
import subprocess
import vendor_absent as v

CONFIG = {'year': 2026, 'spreadsheet_id': 'test', 'planning_sheet_id': 123}

def rows():
    return [[] for _ in range(8)] + [['Company', '2026', 'Type', 'Oct-4', 'Oct-18', 'slug'],
        ['Bright Beads', '1', '', 'Paid', 'Paid', 'bright-beads'],
        ['zzCOMPANY NAME', '1', '', 'Paid']]

class ResolutionTests(unittest.TestCase):
    def test_exact_case_whitespace_and_date(self):
        target = v.resolve(rows(), ' bright  BEADS ', 'Oct 4', 2026)
        self.assertEqual((target['row'],target['column'],target['event']), (9,3,'october-04-2026'))
    def test_duplicate_vendor(self):
        data=rows();data.append(data[9][:])
        with self.assertRaises(v.Stop):v.resolve(data,'Bright Beads','Oct 4',2026)
    def test_partial_name_not_guessed(self):
        with self.assertRaisesRegex(v.Stop,'Which vendor'):v.resolve(rows(),'Bright','Oct 4',2026)
    def test_hidden_vendor_excluded(self):
        with self.assertRaises(v.Stop):v.resolve(rows(),'zzCOMPANY NAME','Oct 4',2026)
    def test_wrong_missing_or_ambiguous_dates(self):
        for day in ['10/4', 'Oct 5', 'Oct 4 2027']:
            with self.subTest(day=day),self.assertRaises(v.Stop):v.resolve(rows(),'Bright Beads',day,2026)
        data=rows();data[8].append('Oct-04')
        with self.assertRaises(v.Stop):v.resolve(data,'Bright Beads','Oct 4',2026)
    def test_year_gate_is_not_changed(self):
        data=rows();data[9][1]='0'
        with self.assertRaisesRegex(v.Stop,'publication gate'):v.resolve(data,'Bright Beads','Oct 4',2026)

class OverrideTests(unittest.TestCase):
    def perform(self,before,after=None,write_error=False):
        api=MagicMock();audit=MagicMock()
        if write_error:api.spreadsheets().batchUpdate().execute.side_effect=TimeoutError()
        reads=[before,before,after or {'stringValue':'Absent'}]
        if write_error:reads.append(after or {'stringValue':'Absent'})
        with patch.object(v,'snapshot',return_value=rows()),patch.object(v,'entered',side_effect=reads):
            target=v.override(api,CONFIG,'Bright Beads','Oct 4',audit)
        return api,audit,target
    def test_formula_is_intentionally_replaced_one_cell_only(self):
        before={'formulaValue':'=VLOOKUP(A10,orders,2,FALSE)'}
        api,audit,target=self.perform(before)
        body=api.spreadsheets().batchUpdate.call_args.kwargs['body']
        self.assertEqual(body,{'requests':[{'updateCells':{'range':{'sheetId':123,'startRowIndex':9,
            'endRowIndex':10,'startColumnIndex':3,'endColumnIndex':4},'rows':[{'values':[
            {'userEnteredValue':{'stringValue':'Absent'}}]}],'fields':'userEnteredValue'}}]})
        self.assertEqual(audit.call_args_list[0].args[0]['before'],before)
    def test_other_literal_status_replaced(self):self.perform({'stringValue':'Paid'})
    def test_formula_displaying_absent_still_replaced(self):
        api,_,_=self.perform({'formulaValue':'="Absent"'})
        api.spreadsheets().batchUpdate.assert_called_once()
    def test_already_literal_absent_no_write(self):
        api,_,_=self.perform({'stringValue':'Absent'})
        api.spreadsheets().batchUpdate.assert_not_called()
    def test_changed_target_stops_before_write(self):
        api=MagicMock()
        with patch.object(v,'snapshot',return_value=rows()),patch.object(v,'entered',side_effect=[{}, {'stringValue':'Paid'}]):
            with self.assertRaises(v.Stop):v.override(api,CONFIG,'Bright Beads','Oct 4',MagicMock())
        api.spreadsheets().batchUpdate.assert_not_called()
    def test_formula_readback_not_accepted(self):
        with self.assertRaisesRegex(v.Stop,'readback'):
            self.perform({'stringValue':'Paid'},{'formulaValue':'="Absent"'})
    def test_uncertain_write_readback_success_no_retry(self):
        api,_,_=self.perform({'stringValue':'Paid'},write_error=True)
        self.assertEqual(api.spreadsheets().batchUpdate().execute.call_count,1)
    def test_ambiguity_never_writes(self):
        api=MagicMock()
        with patch.object(v,'snapshot',return_value=rows()),self.assertRaises(v.Stop):
            v.override(api,CONFIG,'Bright','Oct 4',MagicMock())
        api.spreadsheets().batchUpdate.assert_not_called()

class WorkflowTests(unittest.TestCase):
    def workflow(self,failure=False):
        target=v.resolve(rows(),'Bright Beads','Oct 4',2026)
        with patch.object(v,'check_repositories') as pre,patch.object(v,'load_config',return_value=CONFIG),\
             patch.object(v,'service'),patch.object(v,'private_write'),\
             patch.object(v,'override',return_value=target) as override,\
             patch.object(v.subprocess,'run') as run,patch.object(v,'verify_output') as verify:
            if failure:run.side_effect=subprocess.CalledProcessError(1,'production')
            if failure:
                with self.assertRaisesRegex(v.Stop,'Absent was not undone'):v.run('Bright Beads','Oct 4')
                verify.assert_not_called()
            else:
                v.run('Bright Beads','Oct 4');verify.assert_called_once_with(target)
                self.assertEqual(pre.call_count,2)
            override.assert_called_once()
            self.assertEqual(run.call_args.args[0],['bash','-c','./_src/process_orders.sh && ./_src/build.sh all'])
    def test_success_handoff(self):self.workflow()
    def test_production_failure_does_not_undo(self):self.workflow(True)
    def test_preflight_failure_prevents_sheet_access(self):
        with patch.object(v,'check_repositories',side_effect=v.Stop('dirty')),patch.object(v,'service') as service:
            with self.assertRaises(v.Stop):v.run('Bright Beads','Oct 4')
            service.assert_not_called()
    def test_absence_check_scoped_to_vendor(self):
        html='<li class="vendor-absent"><a href="/other/">Other</a> unable to attend</li><li><a href="/bright-beads/">Bright</a></li>'
        self.assertFalse(v.reflects_absence(html,'bright-beads'))
        self.assertTrue(v.reflects_absence(html,'other'))

if __name__=='__main__':unittest.main()
