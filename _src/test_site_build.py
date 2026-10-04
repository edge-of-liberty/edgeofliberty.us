"""Regression checks; publishing is mocked, so tests never commit or push."""
import json
import html
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import site_build as build


class StagingTests(unittest.TestCase):
    def test_new_generated_pages_selected_without_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / '_data').mkdir()
            (repo / '_data/build.json').write_text(json.dumps({
                'dates': {'september-27-2026': {}},
                'vendors': [{'slug': 'new-vendor'}, {'slug': '../escape'},
                            {'slug': '.hidden'}, {'slug': 'scratch'}],
            }))
            expected = {'september-27-2026/index.html', 'september-27-2026/hero.jpg',
                        'new-vendor/index.html'}
            excluded = {
                'september-27-2026/notes.html', 'new-vendor/extra.html',
                'unrelated/index.html', 'scratch/index.html', '.DS_Store',
                'new-vendor/.DS_Store', '_data/private.eml',
                '_src/ORDER_EMAIL_REVIEW.md', '_src/authorize_orders.py',
                '_src/order_email_review.py', '_src/test_authorize_orders.py',
                '_src/test_order_email_review.py', '../escape/index.html',
                '.hidden/index.html',
            }
            with patch.object(build, 'ROOT', repo), patch.object(build, 'tracked', return_value=set()), patch.object(build, 'git', return_value='\0'.join(expected | excluded)):
                self.assertEqual(set(build.publish_paths(repo, 'eol')), expected)

    def test_missing_build_data_does_not_allow_arbitrary_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(build.generated_eol_pages(Path(temp)), set())

    def test_sources_and_local_files(self):
        known = {'chh/index.html', 'chh/blue/index.html', 'index.html', '_data/build.json', '_layouts/default.html'}
        for path in ['chh/blue/rentedUntil.txt', 'chh/blue/description.txt', 'chh/blue/new.jpg', '_src/site_build.py', '_data/build.json', '_layouts/default.html']:
            self.assertTrue(build.eol_allowed(path, known), path)
        for path in ['BCF.code-workspace', '.env', '.vscode/settings.json', 'scratch.html', 'notes.txt', 'chh/blue/temp.html', '_permits/private.pdf', 'chh/_tmp/test.html', 'chh/blue/.draft.html', 'chh/blue/temp/test.html', '_src/local.py', '_data/local.csv']:
            self.assertFalse(build.eol_allowed(path, known), path)

    def test_obsolete_sources_are_selected_only_when_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / build.MANIFEST).write_text('["index.html"]')
            (repo / 'description.txt').write_text('Retained source must not be staged')
            known = build.OBSOLETE_CHH_SOURCES | {'index.html'}
            with patch.object(build, 'tracked', return_value=known), patch.object(build, 'git', return_value='\0'.join(known | {'BCF.code-workspace'})):
                selected = set(build.publish_paths(repo, 'chh'))
            self.assertEqual(selected & build.OBSOLETE_CHH_SOURCES, build.OBSOLETE_CHH_SOURCES - {'description.txt'})
            self.assertNotIn('BCF.code-workspace', selected)

    def test_manifest_paths(self):
        self.assertEqual(build.safe_manifest_names(iter(['blue/index.html', '.nojekyll'])), {'blue/index.html', '.nojekyll'})
        for path in ['../README.md', '/tmp/file.html', '.git/config', 'blue/rentedUntil.txt', '.env']:
            with self.assertRaises(ValueError):
                build.safe_manifest_names([path])

    def test_commit_excludes_unrelated_staged_work(self):
        with patch.object(build, 'publish_paths', return_value=['index.html']), patch.object(build, 'git', return_value='index.html\0notes.txt\0'), patch.object(build, 'run') as run:
            build.publish(Path('/test/repo'), 'eol')
        calls = [c.args for c in run.call_args_list]
        commit = next(c for c in calls if 'commit' in c)
        self.assertIn('--only', commit)
        self.assertNotIn('notes.txt', commit)
        self.assertEqual(calls[-1][-1], 'push')

    def test_empty_selection_never_runs_blanket_add(self):
        with patch.object(build, 'publish_paths', return_value=[]), patch.object(build, 'git', return_value='notes.txt\0'), patch.object(build, 'run') as run:
            build.publish(Path('/test/repo'), 'eol')
        calls = [c.args for c in run.call_args_list]
        self.assertFalse(any('add' in c or 'commit' in c for c in calls))
        self.assertEqual(calls[-1][-1], 'push')

    def test_unchanged_still_retries_push(self):
        with patch.object(build, 'publish_paths', return_value=['index.html']), patch.object(build, 'git', return_value='notes.txt\0'), patch.object(build, 'run') as run:
            build.publish(Path('/test/repo'), 'eol')
        calls = [c.args for c in run.call_args_list]
        self.assertFalse(any('commit' in c for c in calls))
        self.assertEqual(calls[-1][-1], 'push')

    def test_other_repository_attempted_after_failed_push(self):
        with patch.object(sys, 'argv', ['site_build.py', 'all']), patch.object(build, 'check_destination'), patch.object(build, 'build_eol'), patch.object(build, 'build_standalone'), patch.object(build, 'publish', side_effect=[subprocess.CalledProcessError(1, 'git push'), None]) as publish:
            with self.assertRaises(SystemExit):
                build.main()
        self.assertEqual([c.args[1] for c in publish.call_args_list], ['eol', 'chh'])

    def test_build_only_never_publishes(self):
        with patch.object(sys, 'argv', ['site_build.py', 'build-only']), patch.object(build, 'check_destination'), patch.object(build, 'build_eol'), patch.object(build, 'build_standalone'), patch.object(build, 'publish') as publish:
            build.main()
        publish.assert_not_called()


class RenderingTests(unittest.TestCase):
    def test_bedroom_hero_and_actual_gallery_in_both_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'description.txt').write_text('Overview')
            for slug in ['blue', 'green', 'purple', 'teal', 'common-upper']:
                folder = source / slug
                folder.mkdir()
                original = (build.ROOT / 'chh' / slug / 'description.txt').read_text()
                (folder / 'description.txt').write_text(original)
                (folder / 'rentedUntil.txt').write_text('2026-10-09')
                (folder / 'actual.jpg').write_bytes(b'fixture')
                if slug != 'teal':
                    (folder / '00_Collage.png').write_bytes(b'fixture')
                (folder / '01_Collage.webp').write_bytes(b'fixture')
                (folder / 'FutureKitchenCollage.png').write_bytes(b'fixture')
                if slug != 'teal':
                    (folder / '00_BathCollage.png').write_bytes(b'fixture')
            for target in ['eol', 'chh']:
                output = root / target
                subprocess.run([sys.executable, str(build.SRC / 'build_chh.py'),
                                str(source), '--target', target, '--output', str(output),
                                '--as-of', '2026-10-03'], check=True, capture_output=True)
                for slug in ['blue', 'green', 'purple', 'teal']:
                    page = (output / slug / 'index.html').read_text()
                    hero = page.split('<div class="chh-bedroom-hero', 1)[1].split('</div>\n</div>', 1)[0]
                    gallery = page.split('<h3>Gallery</h3>', 1)[1].split('chh-cta-block', 1)[0]
                    self.assertNotIn('Collage', gallery)
                    self.assertIn('src="actual.jpg"', gallery)
                    self.assertNotIn('01_Collage.webp', page)
                    if slug == 'teal':
                        self.assertIn('chh-bedroom-hero--no-image', page)
                        self.assertNotIn('chh-bedroom-visual', page)
                    else:
                        self.assertIn('src="00_Collage.png"', hero)
                        self.assertIn('staged collage', hero)
                        self.assertEqual(page.count('src="00_Collage.png"'), 1)
                    self.assertIn('Available starting 10/11/26', html.unescape(re.sub('<[^>]+>', '', hero)))
                    for fact in ['Queen bed', 'closet', 'TV', 'Mini fridge']:
                        self.assertIn(fact.lower(), hero.lower())
                    self.assertNotIn('Included', hero)
                    self.assertNotIn('<figcaption>', hero)
                    self.assertIn('Now accepting tour requests.', hero)
                    self.assertIn('<li>Shared bathroom</li>', hero)
                    self.assertNotIn('<strong>Bathroom</strong>', hero)
                    self.assertNotIn('Shared with 1 roommate', hero)
                    self.assertNotIn('Lower level', hero)
                    self.assertNotIn('00_BathCollage', hero)
                    self.assertNotIn('FutureKitchenCollage', page)
                    bathroom_copy = 'The shared bathroom is used by just two roommates and includes a shower.'
                    self.assertIn(bathroom_copy, page)
                    if slug == 'teal':
                        self.assertNotIn('chh-bathroom-visual', page)
                        self.assertNotIn('00_BathCollage', page)
                    else:
                        self.assertEqual(page.count('src="00_BathCollage.png"'), 1)
                        self.assertLess(page.index(bathroom_copy), page.index('src="00_BathCollage.png"'))
                        self.assertLess(page.index('src="00_BathCollage.png"'), page.index('Each room includes'))
                    # Descriptive paragraphs/highlights stay authored, in their original order.
                    original = (source / slug / 'description.txt').read_text()
                    cursor = page.index('chh-bedroom-hero')
                    for line in original.split('Price:', 1)[0].splitlines():
                        if not line.strip():
                            continue
                        content = line.removeprefix('## ').removeprefix('- ')
                        if 'house guest rules' in content:
                            content = content.split('house guest rules')[0]
                        cursor = page.index(html.escape(content), cursor)
                    self.assertEqual(page.count('chh-cta-block'), 1)
                    self.assertLess(page.index('chh-bedroom-hero'), page.index('<h2>Room Highlights'))
                    self.assertLess(page.index('<h2>Room Highlights'), page.index('<h3>Gallery'))
                    self.assertLess(page.index('<h3>Gallery'), page.index('chh-cta-block'))
                common = (output / 'common-upper' / 'index.html').read_text()
                self.assertNotIn('chh-bedroom-hero', common)
                self.assertEqual(common.count('chh-cta-block'), 2)
                for name in ['00_Collage.png', '00_BathCollage.png', '01_Collage.webp', 'FutureKitchenCollage.png', 'actual.jpg']:
                    self.assertIn(f'src="{name}"', common)

    def test_same_content_both_targets_and_availability_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'description.txt').write_text('Shared overview')
            # Friday -> Sunday; Sunday -> following Sunday; blank; past.
            for slug, value in [('blue', '2026-09-18'), ('green', '2026-09-20'), ('purple', ''), ('teal', '2026-09-01')]:
                folder = source / slug
                folder.mkdir()
                (folder / 'description.txt').write_text('Shared room\nPrice: $800/month; additional partial weeks after the initial full month: $200/week')
                (folder / 'rentedUntil.txt').write_text(value)
            for target in ['eol', 'chh']:
                subprocess.run([sys.executable, str(build.SRC / 'build_chh.py'), str(source), '--target', target, '--output', str(root / target), '--as-of', '2026-09-18'], check=True, capture_output=True)
            expected = {'blue': 'Available starting 9/20/26', 'green': 'Available starting 9/27/26', 'purple': 'Available now', 'teal': 'Available now'}
            for slug, label in expected.items():
                eol = (root / 'eol' / slug / 'index.html').read_text()
                chh = (root / 'chh' / slug / 'index.html').read_text()
                self.assertIn(label, eol)
                self.assertIn(label, chh)
                body = eol.split('---', 2)[2].strip()
                normalized = body.replace('https://www.edgeofliberty.us/chh/', 'https://www.createhappinesshouse.com/').replace('/chh/', '/').replace('href="/things-to-do-valparaiso-weekends/"', 'href="https://www.edgeofliberty.us/things-to-do-valparaiso-weekends/"')
                self.assertIn(normalized, chh)
                for schema in re.findall(r'<script type="application/ld\+json">(.*?)</script>', chh, re.S):
                    json.loads(schema)
            self.assertNotIn('<!DOCTYPE', (root / 'eol/index.html').read_text())
            self.assertIn('<!DOCTYPE', (root / 'chh/index.html').read_text())


class ApprovedPolicyTests(unittest.TestCase):
    # Approved 23b4d5a terms, with only the subsequently approved animal changes.
    EXPECTED_TERMS = [
        'These terms summarize the house rules and resident responsibilities for Create Happiness House. They are intended to be included with, referenced by, or attached to the signed rental agreement. If the signed rental agreement says something different, the signed agreement controls.',
        'This page is practical house policy, not legal advice. Rules may be adjusted in writing when required by law or approved by the property owner.',
        'Before You Tour or Apply',
        'A shared house is a little different from renting an apartment. Create Happiness House rents private furnished bedrooms to unrelated adult residents who share a kitchen, bathrooms, laundry, and common spaces. Before anyone commits, we want prospective residents to understand how the house works.',
        'We consider the usual rental qualifications, including ability to pay and screening results, along with whether applicants understand and are willing to follow the house rules and shared-space arrangements described below.',
        'Meeting the basic screening requirements does not guarantee that a room will be offered. We may consider multiple qualified applicants before offering a room.',
        'Length of Stay',
        "All rooms have a 1-month minimum. After the initial full month, you can stay for additional months or add partial weeks at your room's listed weekly extension rate. For example: 1 month, 1 month + 1 week, 1 month + 2 weeks, or 2 months. Weekly rates are not standalone rentals; stays of only 1, 2, or 3 weeks are not available.",
        'Occupancy',
        'Each rented bedroom is set up for one approved occupant unless a different occupancy arrangement is approved in writing before move-in.',
        'The resident named in the rental agreement is the only person permitted to live in the room.',
        'The home is a quiet shared residence with a shared kitchen, bathrooms, laundry, parking, and common areas.',
        'Overnight guests require advance written permission.',
        "Guests are the resident's responsibility and must follow house rules while on the property.",
        'No parties, events, or unapproved gatherings.',
        'Pets and Assistance Animals',
        'Pets are not permitted.',
        'Assistance animals are not treated as pets when an accommodation is required under applicable housing law.',
        'Requests for an assistance-animal accommodation are considered individually.',
        'Quiet Use and Shared Spaces',
        "These expectations help everyone live comfortably in a shared home. When deciding whether to offer or renew a room, we may consider an applicant's agreement to these expectations and a resident's record of following them. We focus on specific housing-related conduct, such as cleaning up, observing quiet hours, and following guest and parking rules, and apply these expectations consistently.",
        "Respect other residents' privacy and belongings. Do not enter another resident's room or use their belongings without permission.",
        'Treat other residents, contractors, owners and property representatives, and guests respectfully.',
        'Communicate reasonably and respectfully about household issues, and bring unresolved concerns to the owners or property representatives.',
        "Do not substantially interfere with another resident's reasonable use and enjoyment of the house.",
        'Follow the guest rules under Occupancy and the parking and shared-property rules under Parking and Property Access.',
        'Quiet hours are 9:00 p.m. to 8:00 a.m.',
        'Residents must keep music, TV, phone calls, and conversations at a respectful volume at all times.',
        'Clean up after yourself in the shared kitchen, bathrooms, laundry areas, and sitting areas after each use.',
        'Food must be stored in assigned or appropriate areas.',
        'Residents may not block hallways, exits, stairs, driveways, or shared access areas.',
        'Smoking, vaping, candles, incense, and open flames are not permitted inside the house.',
        'Parking and Property Access',
        'Parking is limited to approved vehicles in approved parking areas.',
        'The resident must provide current vehicle information if requested.',
        'Do not park on grass, block driveways, block other vehicles, or use areas not designated for resident parking.',
        'Garage parking and garage storage are not included unless specifically approved in writing.',
        'Keys, entry codes, and access information may not be copied or shared.',
        'Care of Furnishings and Inventory',
        'Rooms are furnished and stocked for normal residential use.',
        'Residents are responsible for damage beyond ordinary wear and tear.',
        'Missing items, damaged items, excessive cleaning, smoke odor, pet odor, stains, or misuse may be charged to the resident.',
        'Residents may not remove furniture, linens, kitchen items, decor, appliances, electronics, or supplies from the property.',
        'Any maintenance issue, leak, broken item, pest concern, or safety concern should be reported promptly.',
        'Move-Out Expectations',
        'Remove all personal belongings, food, and trash.',
        'Return keys and any access items.',
        'Leave the room, bathroom areas, kitchen areas, laundry areas, and common spaces reasonably clean.',
        'Do not leave furniture, boxes, clothing, appliances, or unwanted items behind.',
        'Charges may apply for missing items, damaged items, abandoned property, excessive cleaning, or disposal.',
        'Replacement and Damage Costs',
        'The following list gives typical replacement or repair charges. Actual charges may be higher when the real cost of replacement, repair, delivery, installation, professional cleaning, or disposal is higher.',
        'Room key or entry item: $25 each',
        'Lock rekey caused by lost key or shared access: $150 and up',
        'Bath towel: $15 each',
        'Hand towel or washcloth: $8 each',
        'Sheet set: $45 each',
        'Pillow: $25 each',
        'Mattress protector: $40 each',
        'Comforter or quilt: $90 each',
        'Shower curtain or liner: $20 each',
        'Shower caddy: $15 each',
        'Mini fridge: $175 and up',
        'TV or remote: $175 and up',
        'Desk chair: $75 and up',
        'Desk, vanity, dresser, nightstand, or shelving: actual replacement cost',
        'Lamp: $35 each',
        'Trash can: $20 each',
        'Laundry basket or hamper: $20 each',
        'Kitchen cookware, bakeware, dishes, utensils, or small appliances: actual replacement cost',
        'Excessive room cleaning: $75 and up',
        'Excessive common-area cleaning caused by resident or guest: $75 and up',
        'Stain removal, odor treatment, or carpet/upholstery cleaning: actual professional cost',
        'Wall, door, trim, floor, fixture, appliance, plumbing, or electrical damage: actual repair cost',
        'Abandoned-property removal or disposal: $50 and up',
        'Important Fair Housing Note',
        'Create Happiness House follows applicable federal, state, and local fair housing requirements. Rules are intended to protect quiet enjoyment, safety, property condition, and shared-house function, and should be applied consistently.',
    ]

    def test_canonical_sources_regenerate_approved_policies_in_both_sites(self):
        rates = {'blue': ('850', '250'), 'green': ('1000', '290'),
                 'purple': ('1200', '350'), 'teal': ('1500', '425')}
        expected_pages = {'index.html', 'rental-terms/index.html',
                          *{f'{slug}/index.html' for slug in rates},
                          'common-upper/index.html', 'common-lower/index.html',
                          'common-other/index.html', 'travel-nurse-friendly/index.html'}
        def visible(text):
            return html.unescape(re.sub('<[^>]+>', '', text))
        with tempfile.TemporaryDirectory() as temp:
            outputs = {}
            for target, prefix in [('chh', ''), ('eol', '/chh')]:
                output = Path(temp) / target
                command = [sys.executable, str(build.SRC / 'build_chh.py'),
                           str(build.ROOT / 'chh'), '--target', target, '--output', str(output),
                           '--as-of', '2026-09-30']
                subprocess.run(command, check=True, capture_output=True)
                pages = {p.relative_to(output).as_posix(): p.read_text() for p in output.rglob('index.html')}
                self.assertEqual(set(pages), expected_pages)
                terms_page = pages['rental-terms/index.html']
                body = terms_page.split('<h1>Rental Terms &amp; House Rules</h1>', 1)[1].split('</section>', 1)[0]
                actual_terms = [html.unescape(v) for _, v in re.findall(r'<(p|h2|li)(?: [^>]*)?>(.*?)</\1>', body, re.S)]
                self.assertEqual(actual_terms, self.EXPECTED_TERMS)
                for anchor in ['before-you-apply', 'guest-rules', 'shared-house-expectations']:
                    self.assertIn(f'id="{anchor}"', terms_page)
                offers = []
                for name, page in pages.items():
                    for obsolete in ['kitchens', 'weekly and monthly', 'by the week or month',
                                     'best weekly value', 'Unapproved animals', 'private gatherings or overnight guests']:
                        self.assertNotIn(obsolete.lower(), page.lower(), name)
                    self.assertNotRegex(page, r'\$[\d,]+/week or')
                    tour_count = page.count('>Request a Tour</a>')
                    self.assertEqual(tour_count, page.count(f'href="{prefix}/rental-terms/#before-you-apply"'))
                    if tour_count:
                        self.assertIn('Private bedrooms, shared living. Before requesting a tour, read how we offer rooms and what to expect in the house.', visible(page))
                    for payload in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
                        data = json.loads(payload)
                        offers.extend([data] if data.get('@type') == 'Offer' else data.get('makesOffer', []))
                self.assertEqual(len(offers), 24)
                for offer in offers:
                    slug = offer['url'].rstrip('/').split('/')[-1]
                    monthly, weekly = offer['priceSpecification']
                    self.assertEqual((monthly['price'], weekly['price']), rates[slug])
                    self.assertEqual((monthly['unitText'], weekly['unitText']), ('month', 'week'))
                    self.assertEqual(monthly['description'], 'Monthly rent with a 1-month minimum.')
                    self.assertEqual(weekly['name'], 'Additional partial weeks after the initial full month')
                    self.assertEqual(weekly['description'], 'Extension rate only after completing the initial full-month minimum; not a standalone weekly rental rate.')
                    self.assertEqual(offer['description'], '1-month minimum. Weekly rates apply only to additional partial weeks after the initial full month.')
                    self.assertEqual(offer['eligibleDuration'], {'@type': 'QuantitativeValue', 'minValue': 1, 'unitText': 'month'})
                for slug, (monthly, weekly) in rates.items():
                    room = pages[f'{slug}/index.html']
                    self.assertIn(f'${int(monthly):,}/month</strong><span>1-month minimum', room)
                    self.assertIn(f'Additional weeks: ${weekly}/week', visible(room))
                    self.assertIn(f'<p class="chh-room-price">${int(monthly):,}/month</p>', pages['index.html'])
                    self.assertIn(f'1-month minimum. Additional partial weeks after the initial full month: ${weekly}/week.', visible(pages['index.html']))
                self.assertIn(f'<a href="{prefix}/rental-terms/#guest-rules">house guest rules</a>', pages['teal/index.html'])
                self.assertIn('Twin sized day bed and coffee table for relaxing or hosting guests in keeping with the house guest rules', visible(pages['teal/index.html']))
                self.assertIn('Monthly rentals with a 1-month minimum.', pages['index.html'])
                self.assertIn('with a 1-month minimum.', pages['travel-nurse-friendly/index.html'])
                self.assertIn("After the initial full month, add partial weeks at your room's listed extension rate or stay for additional months.", visible(pages['travel-nurse-friendly/index.html']))
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(pages, {p.relative_to(output).as_posix(): p.read_text() for p in output.rglob('index.html')})
                outputs[target] = pages
            for name, eol in outputs['eol'].items():
                body = eol.split('---', 2)[2].strip()
                normalized = body.replace('https://www.edgeofliberty.us/chh/', 'https://www.createhappinesshouse.com/').replace('/chh/', '/').replace('href="/things-to-do-valparaiso-weekends/"', 'href="https://www.edgeofliberty.us/things-to-do-valparaiso-weekends/"')
                self.assertIn(normalized, outputs['chh'][name])


if __name__ == '__main__':
    unittest.main()
