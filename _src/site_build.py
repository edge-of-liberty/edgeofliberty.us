#!/usr/bin/env python3
"""Repository-aware build and publishing behind ./_src/build.sh."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / '_src'
SETTINGS = json.loads((SRC / 'sites.json').read_text())
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.ico'}
WEB_EXTS = IMAGE_EXTS | {'.html', '.css', '.js', '.svg', '.pdf'}
MANIFEST = '.chh-generated.json'
# One-time conversion: allow only deletions of these obsolete standalone sources.
OBSOLETE_CHH_SOURCES = {
    'description.txt', 'common-upper/kitchenStock.txt',
    *{f'{slug}/description.txt' for slug in (
        'blue', 'green', 'purple', 'teal', 'common-lower', 'common-upper',
        'common-other', 'rental-terms', 'travel-nurse-friendly')},
    *{f'{slug}/rentedUntil.txt' for slug in ('blue', 'green', 'purple', 'teal')},
}
TOOL_FILES = {
    '_src/build.sh', '_src/build_chh.py', '_src/build_dates.py', '_src/build_home.py',
    '_src/build_permits.py', '_src/build_vendors.py', '_src/parse_csv.py',
    '_src/render_markdownish.py', '_src/chh_output.py', '_src/site_build.py',
    '_src/sites.json', '_src/templates/chh.html', '_src/templates/chh-404.html',
    '_src/test_site_build.py',
    '_src/google_sheets.py', '_src/fetch_planning_sheet.py',
    '_src/google_sheets.example.json', '_src/requirements-sheets.txt',
    '_src/test_google_sheets.py',
}


def run(*args, cwd=ROOT, capture=False):
    return subprocess.run([str(a) for a in args], cwd=cwd, check=True,
                          text=True, stdout=subprocess.PIPE if capture else None)


def git(repo, *args):
    return run('git', '-C', repo, *args, capture=True).stdout


def tracked(repo):
    return set(filter(None, git(repo, 'ls-files', '-z').split('\0')))


def write_sitemap(output, urls, jekyll=False):
    text = '---\nlayout: null\n---\n' if jekyll else ''
    text += '<?xml version="1.0" encoding="UTF-8"?>\n'
    text += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    text += ''.join(f'  <url><loc>{escape(url)}</loc></url>\n' for url in sorted(set(urls)))
    output.write_text(text + '</urlset>\n')


@contextmanager
def planning_snapshot():
    """One fresh, validated, invocation-specific CSV; never fall back to old data."""
    python = ROOT / '.venv-sheets/bin/python'
    if not python.is_file():
        raise RuntimeError('Sheets environment missing. Create .venv-sheets and install _src/requirements-sheets.txt; see README.md.')
    python_command = [str(python)]
    if sys.platform == 'darwin':
        # An Intel Homebrew bash can launch the build under Rosetta. The Sheets
        # venv was installed natively; run its compiled dependencies natively too.
        arm = subprocess.run(['/usr/sbin/sysctl', '-n', 'hw.optional.arm64'],
                             capture_output=True, text=True)
        if arm.returncode == 0 and arm.stdout.strip() == '1':
            python_command = ['/usr/bin/arch', '-arm64', str(python)]
    local = ROOT / '_local/google-sheets'
    local.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='build-', dir=local) as temp:
        output = Path(temp) / 'planning.csv'
        print('[INFO] Retrieving one fresh Planning snapshot from Google Sheets...', flush=True)
        result = run(*python_command, SRC / 'fetch_planning_sheet.py', 'snapshot', '--output', output, capture=True)
        receipt = json.loads(result.stdout)
        if receipt.get('path') != str(output.resolve()) or not output.is_file():
            raise RuntimeError('Sheets retrieval did not return the expected fresh snapshot.')
        print('[OK] Fresh Planning snapshot validated; using it for this build.', flush=True)
        yield output, str(receipt['year'])


def build_component(name, as_of, planning_csv=None, year=None):
    if name == 'chh':
        run(sys.executable, SRC / 'build_chh.py', ROOT / 'chh', '--as-of', as_of)
        return
    if planning_csv is None:
        with planning_snapshot() as (snapshot, snapshot_year):
            build_component(name, as_of, snapshot, snapshot_year)
        return
    if name == 'permits':
        probe = subprocess.run([sys.executable, '-c', 'import pypdf, reportlab'], capture_output=True)
        if probe.returncode:
            for options in ([], ['--user'], ['--break-system-packages']):
                result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *options, 'pypdf', 'reportlab'])
                if result.returncode == 0:
                    break
            else:
                raise RuntimeError('Could not install permit dependencies: pypdf and reportlab')
    data = run(sys.executable, SRC / 'parse_csv.py', planning_csv, year, capture=True).stdout
    json.loads(data)  # Do not replace valid data with a failed/empty parse.
    (ROOT / '_data/build.json').write_text(data)
    run(sys.executable, SRC / f'build_{name}.py', ROOT, ROOT / '_data/build.json')


def build_eol(as_of):
    with planning_snapshot() as (snapshot, year):
        for name in ('vendors', 'dates', 'home', 'chh', 'permits'):
            build_component(name, as_of, snapshot, year)
    # Preserve existing public routes and add every generated nested CHH page.
    paths = {p for p in tracked(ROOT) if p.endswith('.html') and not p.startswith(('_', '.'))}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'chh').glob('*/index.html'))
    paths.update(p.relative_to(ROOT).as_posix() for p in ROOT.glob('*/index.html')
                 if not p.parent.name.startswith(('_', '.')))
    urls = [SETTINGS['eol']['url'] + '/' + p.removesuffix('index.html') for p in paths]
    write_sitemap(ROOT / 'sitemap.xml', urls, jekyll=True)


def check_destination(destination):
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents or destination in ROOT.parents:
        raise ValueError('Standalone destination must be separate from the source repository')
    if Path(git(destination, 'rev-parse', '--show-toplevel').strip()).resolve() != destination:
        raise ValueError('Standalone destination must be a repository root')
    cname = destination / 'CNAME'
    if not cname.exists() or cname.read_text().strip() != 'www.createhappinesshouse.com':
        raise ValueError('Standalone destination must have the expected CHH CNAME')


def safe_manifest_names(names):
    names = list(names)
    for name in names:
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or any(x.startswith('.') for x in p.parts):
            if name != '.nojekyll':
                raise ValueError(f'Unsafe generated path: {name}')
        if not (p.suffix.lower() in WEB_EXTS or name in {'CNAME', 'robots.txt', 'sitemap.xml', '.nojekyll'}):
            raise ValueError(f'Unexpected generated path: {name}')
    return set(names)


def build_standalone(destination, as_of):
    check_destination(destination)
    with tempfile.TemporaryDirectory(prefix='chh-build-') as temp:
        output = Path(temp)
        run(sys.executable, SRC / 'build_chh.py', ROOT / 'chh', '--target', 'chh',
            '--output', output, '--as-of', as_of)
        source = ROOT / 'chh'
        assets = [source / 'hero.jpg']
        for folder in source.iterdir():
            if folder.is_dir() and (folder / 'description.txt').exists() and not folder.name.startswith(('.', '_')):
                assets.extend(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        for asset in assets:
            target = output / asset.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(asset, target)
        for name in ('css/site.css', 'favicon.ico', 'favicon-512.png'):
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        shutil.copyfile(SRC / 'templates/chh-404.html', output / '404.html')
        (output / 'CNAME').write_text('www.createhappinesshouse.com\n')
        (output / '.nojekyll').write_text('')
        (output / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + SETTINGS['chh']['url'] + '/sitemap.xml\n')
        pages = sorted(output.rglob('index.html'))
        write_sitemap(output / 'sitemap.xml', [SETTINGS['chh']['url'] + '/' + p.relative_to(output).as_posix().removesuffix('index.html') for p in pages])
        validate_standalone(output)
        names = safe_manifest_names(p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file())
        previous = safe_manifest_names(json.loads((destination / MANIFEST).read_text())) if (destination / MANIFEST).exists() else set()
        # Never follow destination symlinks or delete files outside the owned manifest.
        for name in names | previous:
            target = destination / name
            if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != destination.parent):
                raise ValueError(f'Symlink in output destination: {name}')
        for name in sorted(names):
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != (output / name).read_bytes():
                shutil.copyfile(output / name, target)
        for name in previous - names:
            (destination / name).unlink(missing_ok=True)
        (destination / MANIFEST).write_text(json.dumps(sorted(names), indent=2) + '\n')
    print(f'[OK] Standalone output validated and synchronized: {destination}')


def validate_standalone(output):
    from html.parser import HTMLParser
    from urllib.parse import urlsplit, unquote
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key not in ('href', 'src') or not value:
                    continue
                url = urlsplit(value)
                if url.scheme or url.netloc or not url.path:
                    continue
                path = output / unquote(url.path).lstrip('/') if url.path.startswith('/') else self.page.parent / unquote(url.path)
                if path.is_dir():
                    path /= 'index.html'
                if not path.exists():
                    raise ValueError(f'Broken link in {self.page.name}: {value}')
    for page in output.rglob('*.html'):
        text = page.read_text()
        if '{%' in text or '{{' in text or '/chh/' in text:
            raise ValueError(f'Unrendered template or wrong CHH prefix: {page}')
        parser = Links()
        parser.page = page
        parser.feed(text)
        if page.name == 'index.html':
            url = SETTINGS['chh']['url'] + '/' + page.relative_to(output).as_posix().removesuffix('index.html')
            if f'rel="canonical" href="{url}"' not in text:
                raise ValueError(f'Incorrect canonical: {page}')


def generated_eol_pages(repo):
    """Exact date/vendor outputs named by the current parsed build data."""
    source = repo / '_data/build.json'
    if not source.is_file():
        return set()
    data = json.loads(source.read_text())
    slugs = set(data.get('dates', {}))
    slugs.update(v.get('slug', '') for v in data.get('vendors', []))
    valid = {slug for slug in slugs
             if isinstance(slug, str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)}
    pages = {f'{slug}/index.html' for slug in valid}
    # Date pages explicitly reference this asset; do not allow arbitrary siblings.
    pages.update(f'{slug}/hero.jpg' for slug in valid if slug in data.get('dates', {}))
    return pages


def eol_allowed(name, known, generated=()):
    p = Path(name)
    if any(part in {'_tmp', '__pycache__'} for part in p.parts):
        return False
    if name in TOOL_FILES:
        return True
    if any(part.startswith('.') or part.lower() in {'tmp', 'temp', 'local', 'scratch', 'vendor'} for part in p.parts):
        return name == '.gitignore'
    if p.stem.lower() in {'tmp', 'temp', 'scratch', 'local', 'draft', 'backup'}:
        return False
    if any(part.lower().endswith(('.tmp', '.bak', '~', '.code-workspace')) for part in p.parts):
        return False
    if p.parts[0] in {'_site', '_permits', '_wget.tmp', '__pycache__'}:
        return False
    if p.parts[0] == '_src':
        return name in known and p.parts[1] == 'assets' and p.suffix == '.pdf'
    if p.parts[0] in {'_data', '_includes', '_layouts'}:
        return name in known
    if len(p.parts) == 1:
        return name in known and (p.suffix.lower() in WEB_EXTS or name in {
            'README.md', 'CNAME', 'robots.txt', 'sitemap.xml', '_config.yaml', 'Gemfile', 'Gemfile.lock'})
    # Existing website directories, or a deliberately authored new page directory.
    site_dir = p.parts[0]
    if site_dir.startswith('_'):
        return False
    if name in generated:
        return True
    established = any(n.startswith(site_dir + '/') and n.endswith('/index.html') for n in known)
    authored = (ROOT / site_dir / 'description.txt').is_file() and (ROOT / site_dir / 'index.html').is_file()
    asset_dir = site_dir in {'images', 'css', 'proof', 'post2'}
    if not (established or authored or asset_dir):
        return False
    return p.suffix.lower() in WEB_EXTS or p.name in {'description.txt', 'blurb.txt', 'rentedUntil.txt', 'kitchenStock.txt'}


def publish_paths(repo, target):
    known = tracked(repo)
    candidates = set(filter(None, git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0')))
    if target == 'chh':
        owned = safe_manifest_names(json.loads((repo / MANIFEST).read_text()))
        # Include removed files owned by the last committed manifest.
        if MANIFEST in known:
            owned |= safe_manifest_names(json.loads(git(repo, 'show', f'HEAD:{MANIFEST}')))
        removed_sources = {name for name in OBSOLETE_CHH_SOURCES & known
                           if not (repo / name).exists() and not (repo / name).is_symlink()}
        return sorted(((owned | {MANIFEST}) & candidates) | removed_sources)
    generated = generated_eol_pages(repo)
    return sorted(n for n in candidates if eol_allowed(n, known, generated))


def publish(repo, target):
    paths = publish_paths(repo, target)
    # Explicit pathspecs protect unrelated pre-staged work as well as untracked files.
    if paths:
        run('git', '--literal-pathspecs', '-C', repo, 'add', '-A', '--', *paths)
    changed = set(filter(None, git(repo, 'diff', '--cached', '--name-only', '-z').split('\0'))) & set(paths)
    if changed:
        run('git', '--literal-pathspecs', '-C', repo, 'commit', '--only', '-m',
            f'Site build {datetime.now():%Y-%m-%d %H:%M:%S}', '--', *sorted(changed))
    else:
        print(f'[OK] {target}: no website changes to commit')
    # Always retry pending commits; an unchanged tree is not an error.
    run('git', '-C', repo, 'push')
    print(f'[OK] {target}: push complete')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['all', 'build-only', 'eol', 'chh-site', 'chh-build', 'vendors', 'dates', 'home', 'chh', 'permits', 'staging-preview'])
    parser.add_argument('--chh-repo', type=Path, default=Path(os.environ.get('CHH_REPO', str(ROOT.parent / 'createhappinesshouse.com'))))
    args = parser.parse_args()
    destination = args.chh_repo.resolve()
    as_of = date.today().isoformat()
    if args.command == 'staging-preview':
        for repo, target in [(ROOT, 'eol'), (destination, 'chh')]:
            allowed = set(publish_paths(repo, target))
            changed = set(filter(None, git(repo, 'diff', 'HEAD', '--name-only', '-z').split('\0')))
            changed |= set(filter(None, git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')))
            print(json.dumps({'repository': str(repo), 'included': sorted(changed & allowed), 'excluded': sorted(changed - allowed)}, indent=2))
        return
    if args.command in {'vendors', 'dates', 'home', 'chh', 'permits'}:
        build_component(args.command, as_of)
        return
    targets = []
    if args.command in {'all', 'build-only', 'chh-site', 'chh-build'}:
        check_destination(destination)
    if args.command in {'all', 'build-only', 'eol'}:
        build_eol(as_of)
        targets.append((ROOT, 'eol'))
    if args.command in {'all', 'build-only', 'chh-site', 'chh-build'}:
        build_standalone(destination, as_of)
        targets.append((destination, 'chh'))
    if args.command in {'build-only', 'chh-build'}:
        print('[OK] Build only: no staging, commits, or pushes')
        return
    failed = []
    for repo, target in targets:
        try:
            publish(repo, target)
        except (subprocess.CalledProcessError, ValueError, OSError) as exc:
            failed.append(target)
            print(f'[ERROR] {target}: {exc}', file=sys.stderr)
    if failed:
        raise SystemExit('Publication failed for: ' + ', '.join(failed))


if __name__ == '__main__':
    main()
