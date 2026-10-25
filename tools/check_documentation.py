#!/usr/bin/env python3
"""Check repository Markdown targets, anchors and bilingual examples."""
from html import unescape
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def without_code(text):
    return re.sub(r'(?ms)^(```|~~~).*?^\1[^\n]*$', '', text)


def anchors(text):
    found = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    counts = {}
    for heading in re.findall(r'(?m)^#{1,6}\s+(.+?)\s*#*$', without_code(text)):
        heading = re.sub(r'<[^>]+>', '', unescape(heading))
        slug = re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-')
        number = counts.get(slug, 0)
        counts[slug] = number + 1
        found.add(slug + ('-' + str(number) if number else ''))
    return found


def main():
    files = [p for p in ROOT.rglob('*.md') if '.git' not in p.parts]
    errors = []
    pairs = 0
    for path in files:
        text = path.read_text(encoding='utf-8')
        body = without_code(text)
        links = re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)', body)
        links += re.findall(r'(?:href|src)=["\']([^"\']+)', body)
        for raw in links:
            raw = unescape(raw)
            url = urlsplit(raw)
            if url.scheme or url.netloc or raw.startswith('/'):
                continue
            target = path.parent / unquote(url.path) if url.path else path
            if not target.exists():
                errors.append(f'{path.relative_to(ROOT)}: missing {raw}')
            elif url.fragment and target.suffix == '.md':
                if unquote(url.fragment) not in anchors(target.read_text(encoding='utf-8')):
                    errors.append(f'{path.relative_to(ROOT)}: missing anchor {raw}')
        if path.stem.endswith('_TR'):
            english = path.with_name(path.stem[:-3] + '.md')
            if not english.exists():
                errors.append(f'{path.relative_to(ROOT)}: missing English pair')
                continue
            pairs += 1
            source = english.read_text(encoding='utf-8')
            blocks = lambda value: re.findall(r'(?ms)^```[^\n]*\n(.*?)^```', value)
            if blocks(source) != blocks(text):
                errors.append(f'{path.relative_to(ROOT)}: code blocks differ')
            images = lambda value: re.findall(r'(?:src=["\']|!\[[^\]]*\]\()([^\s"\')]+)', value)
            if images(source) != images(text):
                errors.append(f'{path.relative_to(ROOT)}: image order differs')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Checked {len(files)} Markdown files, {pairs} EN/TR pairs: links, anchors, code blocks and image order OK.')


if __name__ == '__main__':
    main()
