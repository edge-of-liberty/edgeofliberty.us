"""Frozen legacy recovery links: local snapshots only, never network discovery."""
from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET

SITEMAPS = ('post-sitemap.xml', 'page-sitemap.xml', 'page-sitemap2.xml')


def render_links(data_dir):
    urls = set()
    for name in SITEMAPS:
        for node in ET.parse(Path(data_dir) / name).findall('{*}url/{*}loc'):
            if node.text and node.text.strip():
                urls.add(node.text.strip().rstrip('/'))
    return '<ul> \n' + ''.join(
        f'<li><a href="{escape(url, quote=True)}">{escape(url)}</a></li>\n'
        for url in sorted(urls)) + '</ul>\n'


def build(root):
    root = Path(root)
    (root / '_includes/old_site_links.html').write_text(render_links(root / '_data'))
