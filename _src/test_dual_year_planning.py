"""Offline dual-season acquisition, identity and rendered-page regressions."""
import copy
import csv
from datetime import date, datetime
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import dual_year_planning as dual
from google_sheets import SheetsError

ROOT = Path(__file__).resolve().parent.parent
DATES27 = ['May-16','May-30','Jun-13','Jun-27','Jul-11','Jul-25','Aug-8','Aug-22','Sep-5','Sep-19','Oct-3','Oct-17','Oct-31']


def parse(year, entries, dates=None):
    dates = dates or (DATES27 if year == 2027 else ['Nov-1', 'Oct-18'])
    # The inserted year column and reordered metadata exercise header independence.
    headers = ['Company', '2026'] + (['2027'] if year == 2027 else []) + ['Type','slug','Short Description'] + dates
    rows = [[] for _ in range(8)] + [headers]
    rows[1] = ['4' if h in dates else '' for h in headers]
    for fields in entries:
        rows.append([fields.get(h, '') for h in headers])
    buf = io.StringIO(); csv.writer(buf).writerows(rows)
    result = subprocess.run([sys.executable,'-B',str(ROOT/'_src/parse_csv.py'),'/dev/stdin',str(year),'--identities'],input=buf.getvalue(),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def entry(name, year, active='1', **extra):
    return dict({'Company':name,'slug':name.lower().replace(' ','-'),str(year):active}, **extra)


class IdentityTests(unittest.TestCase):
    def test_header_shift_identity_and_independent_years(self):
        a=parse(2026,[entry('Both',2026,**{'Nov-1':'Paid','Oct-18':'Absent'}),entry('Old',2026,**{'Nov-1':'Paid'}),entry('Neither',2026,'0',**{'Nov-1':'Paid'})])
        b=parse(2027,[entry('Both',2027,**{'May-16':'Paid'}),entry('New',2027,**{'May-16':'Paid'}),entry('Neither',2027,'0',**{'May-16':'Paid'})])
        d=dual.merge([(2026,a),(2027,b)]);v={v['slug']:v for v in d['vendors']}
        self.assertEqual(len(v),4)
        self.assertEqual(v['both']['participation'],{'2026':True,'2027':True})
        self.assertEqual(len(v['both']['dates']),3)
        self.assertEqual(v['neither']['dates'],[])
        self.assertEqual([x['slug'] for x in d['dates']['may-16-2027']['vendors']],['both','new'])
        self.assertEqual(v['old']['dates'][0]['slug'],'november-01-2026')
    def test_conflicts_and_duplicate_slug_stop(self):
        a=parse(2026,[entry('Both',2026,Type='Sponsor')]);b=parse(2027,[entry('Both',2027,Type='')])
        with self.assertRaisesRegex(SheetsError,'Type conflict.*both'):dual.merge([(2026,a),(2027,b)])
        a['vendors'].append(copy.deepcopy(a['vendors'][0]))
        with self.assertRaisesRegex(SheetsError,'duplicate'):dual.merge([(2026,a)])
        a['vendors'].pop();b['vendors'][0]['type']='Sponsor';b['vendors'][0]['name']='Different'
        with self.assertRaisesRegex(SheetsError,'Ambiguous'):dual.merge([(2026,a),(2027,b)])
    def test_established_metadata_wins_and_empty_fields_fill(self):
        a=parse(2026,[entry('Both',2026,**{'Short Description':'Established'})]);b=parse(2027,[entry('Both',2027,**{'Short Description':'Changed'})])
        a['vendors'][0]['website']='';b['vendors'][0]['website']='https://example.com'
        v=dual.merge([(2026,a),(2027,b)])['vendors'][0]
        self.assertEqual(v['short_description'],'Established');self.assertEqual(v['website'],'https://example.com')
    def test_real_participant_examples(self):
        names=['Batshit Crazy Farms','The Edge of Liberty']
        a=parse(2026,[entry(n,2026,**{'Nov-1':'Paid'}) for n in names])
        b=parse(2027,[entry(n,2027,**{h:'Paid' for h in DATES27}) for n in names])
        data=dual.merge([(2026,a),(2027,b)])
        self.assertEqual([v['name'] for v in data['vendors']],names)
        self.assertTrue(all(len(v['dates'])==14 for v in data['vendors']))
    def test_hidden_and_blank_company_excluded(self):
        self.assertEqual(parse(2027,[entry('zzCOMPANY NAME',2027),entry('',2027)])['vendors'],[])


class AcquisitionTests(unittest.TestCase):
    def test_native_date_year_validation(self):
        cell={'effectiveValue':{'numberValue':46523},'effectiveFormat':{'numberFormat':{'type':'DATE'}}}
        dual.validate_date_cells(['May-16'],[cell],2027,'2027 Craft Fair Planning')
        with self.assertRaisesRegex(SheetsError,'underlying date'):dual.validate_date_cells(['May-16'],[cell],2026,'wrong')
        with self.assertRaises(SheetsError):dual.validate_date_cells(['May-16'],[{}],2027,'missing')
    def test_exact_sources_and_year_pairing(self):
        service=MagicMock();props=[{'properties':{'sheetId':sid,'title':title}} for year,sid,title in dual.SOURCES]
        native={'sheets':[{'data':[{'rowData':[{'values':[]}]}]}]}
        service.spreadsheets().get().execute.side_effect=[{'sheets':props},native,native]
        rows=[[] for _ in range(8)]+[['Company','slug']]
        empty={'vendors':[],'dates':{}}
        with patch.object(dual,'planning_values',return_value=rows) as fetch,patch.object(dual,'validate_date_cells') as validate,patch.object(dual.subprocess,'run',return_value=type('Result',(),{'returncode':0,'stdout':json.dumps(empty)})()):
            dual.fetch_website(service,{'spreadsheet_id':'test','planning_sheet_id':1777984672,'year':2026})
        self.assertEqual([(c.args[1]['planning_sheet_id'],c.args[1]['year']) for c in fetch.call_args_list],[(1777984672,2026),(514124464,2027)])
        self.assertEqual([c.args[2] for c in validate.call_args_list],[2026,2027])
    def test_wrong_tab_title_stops(self):
        s=MagicMock();s.spreadsheets().get().execute.return_value={'sheets':[{'properties':{'sheetId':1777984672,'title':'Wrong'}}]}
        with self.assertRaisesRegex(SheetsError,'Expected Planning tab'):dual.fetch_website(s,{'spreadsheet_id':'test'})


class RenderingTests(unittest.TestCase):
    def test_two_year_pages_directory_history_and_no_2027_checkout(self):
        a=parse(2026,[entry('Both',2026,**{'Nov-1':'Paid','Oct-18':'Absent'}),entry('Old',2026,**{'Nov-1':'Paid'}),entry('Neither',2026,'0'),entry('Archived',2026,'0')])
        b=parse(2027,[entry('Both',2027,**{h:'Paid' for h in DATES27}),entry('New',2027,**{'May-16':'Paid'}),entry('Neither',2027,'0'),entry('Archived',2027,'0')])
        data=dual.merge([(2026,a),(2027,b)])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'_includes').mkdir();(root/'_data').mkdir()
            (root/'_includes/date_intro.html').write_text('<p>Welcome</p><p>Be a <a href="https://batshitcrazyfarms.com/checkout">vendor</a></p>')
            (root/'archived').mkdir();(root/'archived/index.html').write_text('Existing page')
            path=root/'_data/build.json';path.write_text(json.dumps(data))
            for builder in ['build_vendors.py','build_dates.py']:
                # Freeze only the builder clock; no production data is touched.
                class Clock(date):
                    @classmethod
                    def today(cls):return cls(2026,10,29)
                with patch('sys.argv',[builder,str(root),str(path)]),patch('datetime.date',Clock),patch('sys.stderr',io.StringIO()),patch('sys.stdout',io.StringIO()):
                    runpy.run_path(str(ROOT/'_src'/builder),run_name='__main__')
            for slug in ['both','old','new','archived']:self.assertTrue((root/slug/'index.html').exists())
            self.assertFalse((root/'neither/index.html').exists())
            body=(root/'both/index.html').read_text()
            self.assertLess(body.index('2027 Craft Fairs'),body.index('2026 Craft Fairs'))
            oldcol=body.split('2026 Craft Fairs')[1]
            self.assertLess(oldcol.index('October 18'),oldcol.index('November 01'))
            self.assertEqual(body.count('<h4>2027 Craft Fairs'),1)
            self.assertIn('No dates listed.',(root/'old/index.html').read_text())
            listing=(root/'_includes/home_vendors.html').read_text()
            for slug in ['both','old','new']:self.assertEqual(listing.count(f'href="/{slug}/"'),1)
            self.assertNotIn('href="/neither/"',listing);self.assertNotIn('href="/archived/"',listing)
            upcoming=(root/'_includes/home_dates.html').read_text().split('Market Memories')[0]
            self.assertLess(upcoming.index('November 01, 2026'),upcoming.index('May 16, 2027'))
            self.assertNotIn('October 18, 2026',upcoming)
            for slug in data['dates']:
                p=root/slug/'index.html';self.assertTrue(p.exists())
                if slug.endswith('2027'):
                    text=p.read_text();self.assertNotIn('/ols/',text);self.assertNotIn('/checkout',text);self.assertNotIn('Book a Vendor Booth',text)
                    self.assertIn('/images/event-default.jpg',text)
            self.assertEqual(len(list(root.glob('*-2027/index.html'))),13)
            self.assertIn('unable to attend',(root/'october-18-2026/index.html').read_text())
            self.assertIn('/v/261101',(root/'november-01-2026/index.html').read_text())
        css=(ROOT/'css/site.css').read_text()
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr))',css)
        self.assertIn('.vendor-year-columns { grid-template-columns: 1fr; }',css)


if __name__=='__main__':unittest.main()
