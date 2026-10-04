"""Offline coverage for the exact frozen sitemap inputs."""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import build_legacy_links as legacy

ROOT = Path(__file__).resolve().parents[1]

class LegacyTests(unittest.TestCase):
    def test_each_actual_snapshot_contributes_without_network(self):
        with patch('socket.socket', side_effect=AssertionError('No network permitted')):
            text = legacy.render_links(ROOT / '_data')
        actual = re.findall(r'href="([^"]+)"', text)
        self.assertEqual(actual, sorted(set(actual)))
        for filename in legacy.SITEMAPS:
            urls = [node.text.strip().rstrip('/') for node in
                    ET.parse(ROOT / '_data' / filename).findall('{*}url/{*}loc')]
            self.assertTrue(urls)
            self.assertTrue(set(urls) <= set(actual), filename)
            self.assertIn(f'>{urls[0]}</a>', text)
    def test_normalization_dedupe_sort_escape_and_exact_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '_data').mkdir(); (root / '_includes').mkdir()
            for name, url in zip(legacy.SITEMAPS, ['https://old/z/', 'https://old/a/?x=1&amp;y=2', 'https://old/z']):
                (root / '_data' / name).write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+url+'</loc><image xmlns="other"><loc>https://image/ignore</loc></image></url></urlset>')
            (root / '_data/page-sitemap3.xml').write_text('Not an input')
            legacy.build(root)
            text = (root / '_includes/old_site_links.html').read_text()
            self.assertEqual(text.count('<li>'), 2)
            self.assertIn('x=1&amp;y=2', text)
            self.assertNotIn('https://image/ignore', text)
            self.assertLess(text.index('https://old/a'), text.index('https://old/z'))

if __name__ == '__main__': unittest.main()
