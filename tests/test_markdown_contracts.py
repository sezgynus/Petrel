"""Repository-wide documentation routes and executable bilingual examples.

Mechanical checks complement, rather than claim, semantic/source review.
"""
import ast
from collections import Counter
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGLISH_REFERENCES = {'docs/t5uic1-reference.md', 'docs/source-audit.md',
                      'docs/mmu-driver-integration.md'}
BILINGUAL_SINGLE_FILES = {'docs/assets/screens/README.md'}


def prose(text):
    return re.sub(r'```.*?```', '', text, flags=re.S)


def anchors(text):
    text = prose(text)
    result = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    seen = Counter()
    for heading in re.findall(r'^#{1,6}\s+(.+)', text, re.M):
        value = re.sub(r'<[^>]*>', '', heading).strip().lower()
        value = ''.join(c for c in value if c in '_- ' or unicodedata.category(c)[0] in 'LN')
        value = value.replace(' ', '-')
        index = seen[value]
        seen[value] += 1
        result.add(value + ('-' + str(index) if index else ''))
    return result


class MarkdownContracts(unittest.TestCase):
    def files(self):
        return sorted(p for p in ROOT.rglob('*.md') if '.git' not in p.parts)

    def pairs(self):
        for path in self.files():
            if not path.stem.endswith('_TR'):
                other = path.with_name(path.stem + '_TR.md')
                if other.exists():
                    yield path, other

    def test_local_links_images_and_section_routes_resolve(self):
        for path in self.files():
            text = prose(path.read_text(encoding='utf-8'))
            targets = re.findall(r'\[[^\]]*\]\(([^)]+)\)', text)
            targets += re.findall(r'(?:href|src)=["\']([^"\']+)', text)
            for target in targets:
                if re.match(r'\w+://|mailto:', target):
                    continue
                name, separator, fragment = target.partition('#')
                resolved = (path.parent / unquote(name)).resolve() if name else path
                with self.subTest(document=str(path.relative_to(ROOT)), target=target):
                    self.assertTrue(resolved.exists(), 'Missing local target')
                    if separator and resolved.suffix == '.md':
                        self.assertIn(unquote(fragment), anchors(resolved.read_text(encoding='utf-8')))

    def test_language_pairs_cover_all_guides_except_declared_reference_policy(self):
        for path in self.files():
            relative = str(path.relative_to(ROOT))
            if relative in ENGLISH_REFERENCES | BILINGUAL_SINGLE_FILES:
                continue
            partner = path.with_name(path.stem[:-3] + '.md' if path.stem.endswith('_TR')
                                     else path.stem + '_TR.md')
            self.assertTrue(partner.is_file(), relative)

    def test_bilingual_command_blocks_and_example_images_match(self):
        image_pattern = r'!\[[^\]]*\]\(([^)]+)\)|<img\b[^>]*\bsrc=["\']([^"\']+)'
        for english, turkish in self.pairs():
            first, second = english.read_text(), turkish.read_text()
            with self.subTest(pair=str(english.relative_to(ROOT))):
                self.assertEqual(re.findall(r'```[^\n]*\n(.*?)```', first, re.S),
                                 re.findall(r'```[^\n]*\n(.*?)```', second, re.S))
                self.assertEqual(re.findall(image_pattern, first), re.findall(image_pattern, second))

    def test_discovery_endpoint_contract_is_documented_in_both_languages(self):
        module = ast.parse((ROOT / 'petrel/features/maintenance/discovery/services.py').read_text())
        endpoints = next(ast.literal_eval(node.value) for node in module.body
                         if isinstance(node, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == '_ENDPOINTS' for t in node.targets))
        for suffix in ('', '_TR'):
            text = (ROOT / ('docs/maintenance-discovery' + suffix + '.md')).read_text()
            for endpoint in endpoints:
                self.assertIn('`' + endpoint + '`', text)

