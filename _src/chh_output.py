"""Wrap a shared CHH page body for Jekyll or standalone static hosting."""
from contextlib import contextmanager
from html import escape
from io import StringIO
import json
from pathlib import Path
from string import Template


@contextmanager
def page_writer(path, output, settings):
    buffer = StringIO()
    yield buffer
    text = buffer.getvalue()
    if settings['format'] == 'html':
        _, front, body = text.split('---', 2)
        meta = {}
        for line in front.strip().splitlines():
            key, value = line.split(':', 1)
            value = value.strip()
            meta[key] = json.loads(value) if value.startswith('"') else value
        route = path.relative_to(output).as_posix().removesuffix('index.html')
        url = settings['url'] + '/' + route
        title = meta.get('og_title', meta['title'])
        description = meta.get('og_description', meta.get('description', ''))
        image = meta.get('og_image', meta.get('image'))
        image_tags = ''
        if image:
            image_url = escape(settings['url'] + image, quote=True)
            image_tags = '\n'.join([
                f'  <meta property="og:image" content="{image_url}">',
                f'  <meta property="og:image:secure_url" content="{image_url}">',
                f'  <meta name="twitter:image" content="{image_url}">',
            ])
        template = Template((Path(__file__).parent / 'templates/chh.html').read_text())
        text = template.substitute(
            title=escape(meta['title'], quote=True), social_title=escape(title, quote=True),
            description=escape(description, quote=True), url=escape(url, quote=True),
            image_tags=image_tags, body=body.strip(),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
