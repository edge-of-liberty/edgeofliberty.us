import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import sync_sitemap_sheet as sync
import site_build as build

class SitemapTests(unittest.TestCase):
 def fixture(self,n):
  return [['old',sync.PATTERNS[1].format(row=i),'',sync.PATTERNS[3].format(row=i),'','',sync.PATTERNS[6].format(row=i)] for i in range(1,n+1)]
 def test_xml_lines_preserve_loc_for_existing_split(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'sitemap.xml';p.write_text('---\nlayout: null\n---\n<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n<url><loc>https://example.com/vendor/</loc></url>\n</urlset>\n')
   lines=sync.sitemap_lines(p)
  self.assertEqual(len(lines),6)
  loc=lines[3]
  self.assertEqual(loc.split('>')[1].split('<')[0],'https://example.com/vendor/')
  self.assertNotIn('layout: null','\n'.join(lines))
 def test_growth_and_only_authorized_columns(self):
  report,req=sync.plan(['xml']*5,{'sheetId':1,'gridProperties':{'rowCount':3}},self.fixture(3))
  self.assertEqual(report['formula_fill'],['B4:B5','D4:D5','G4:G5'])
  self.assertEqual(report['rows_to_add'],2)
  for r in req:
   if 'copyPaste' in r:self.assertEqual(r['copyPaste']['pasteType'],'PASTE_FORMULA')
   self.assertNotIn('repeatCell',r)
 def test_shrink_clears_only_values_in_abdg(self):
  report,req=sync.plan(['xml']*2,{'sheetId':1,'gridProperties':{'rowCount':5}},self.fixture(5))
  self.assertEqual(report['input_clear'],'A3:A5')
  self.assertEqual(report['formula_clear'],['B3:B5','D3:D5','G3:G5'])
  clears=[r['updateCells'] for r in req if 'updateCells' in r and 'range' in r['updateCells']]
  self.assertEqual([r['range']['startColumnIndex'] for r in clears],[0,1,3,6])
  self.assertTrue(all(r['fields']=='userEnteredValue' for r in clears))
 def test_offline_preview_never_authorizes(self):
  with patch('sys.argv',['sync_sitemap_sheet.py']),patch.object(sync,'sitemap_lines',return_value=['xml']),patch.object(sync,'client') as client:
   sync.main()
  client.assert_not_called()
 def test_after_both_successful_publishes_only(self):
  for command in ['all','eol','chh-site','chh-build','build-only']:
   events=[]
   with patch('sys.argv',['site_build.py',command]),patch.object(build,'check_destination'),patch.object(build,'build_eol'),patch.object(build,'build_standalone'),patch.object(build,'publish',side_effect=lambda repo,target:events.append(target)),patch.object(build,'sync_sitemap_sheet',side_effect=lambda:events.append('sync')):
    build.main()
   if command=='all':self.assertEqual(events,['eol','chh','sync'])
   else:self.assertNotIn('sync',events)
 def test_failure_never_syncs(self):
  with patch('sys.argv',['site_build.py','all']),patch.object(build,'check_destination'),patch.object(build,'build_eol'),patch.object(build,'build_standalone'),patch.object(build,'publish',side_effect=OSError('failed')),patch.object(build,'sync_sitemap_sheet') as sync_call:
   with self.assertRaises(SystemExit):build.main()
  sync_call.assert_not_called()

if __name__=='__main__':unittest.main()
