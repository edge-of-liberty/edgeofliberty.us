"""Regression checks; publishing is mocked, so tests never commit or push."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import site_build as build


class StagingTests(unittest.TestCase):
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
                (folder / 'description.txt').write_text('Shared room\nPrice: $200/week')
                (folder / 'rentedUntil.txt').write_text(value)
            for target in ['eol', 'chh']:
                subprocess.run([sys.executable, str(build.SRC / 'build_chh.py'), str(source), '--target', target, '--output', str(root / target), '--as-of', '2026-09-18'], check=True, capture_output=True)
            expected = {'blue': 'Available Starting September 20, 2026', 'green': 'Available Starting September 27, 2026', 'purple': 'Available Now', 'teal': 'Available Now'}
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


if __name__ == '__main__':
    unittest.main()
