"""Edition staging: which pages an audience receives, and which assets follow them."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    'manual_builder', Path(__file__).resolve().parents[1] / 'scripts/build_manual.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class CopyPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.docs = self.root / 'docs'
        self.source = self.docs / 'en'
        self.target = self.root / 'staged'
        (self.docs / 'assets/api/home').mkdir(parents=True)
        (self.docs / 'assets/api/home/projects.json').write_text('{"items": []}', encoding='utf-8')
        (self.source / 'modules/access-control').mkdir(parents=True)

    def page(self, relative, audiences, body='', module='access-control'):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        front = 'audiences:\n' + ''.join(f'  - {name}\n' for name in audiences) + f'module: {module}\n'
        path.write_text('---\n' + front + '---\n' + body, encoding='utf-8')
        return path

    def test_shared_assets_follow_the_pages_that_reach_them(self):
        """A manual keeps assets beside its languages; a staged edition must still resolve them."""
        self.page('modules/access-control/home-api.md', ['technical'],
                  'See [the sample](../../../assets/api/home/projects.json).')
        self.assertEqual(builder.copy_pages(self.source, self.target, 'technical', None), 1)
        staged = self.target / 'modules/access-control/home-api.md'
        self.assertIn('../../assets/api/home/projects.json', staged.read_text(encoding='utf-8'))
        self.assertTrue((self.target / 'assets/api/home/projects.json').is_file())

    def test_only_the_selected_audience_and_module_are_staged(self):
        self.page('modules/access-control/admin.md', ['administrator'])
        self.page('modules/access-control/tech.md', ['technical'])
        self.page('modules/billing/other.md', ['technical'], module='billing')
        self.assertEqual(builder.copy_pages(self.source, self.target, 'technical', 'access-control'), 1)
        self.assertTrue((self.target / 'modules/access-control/tech.md').is_file())
        self.assertFalse((self.target / 'modules/access-control/admin.md').exists())
        self.assertFalse((self.target / 'modules/billing/other.md').exists())

    def test_unreached_assets_stay_out_of_the_edition(self):
        (self.docs / 'assets/api/home/unused.json').write_text('{}', encoding='utf-8')
        self.page('modules/access-control/tech.md', ['technical'],
                  'See [the sample](../../../assets/api/home/projects.json).')
        builder.copy_pages(self.source, self.target, 'technical', None)
        self.assertFalse((self.target / 'assets/api/home/unused.json').exists())

    def test_a_missing_asset_fails_where_it_can_be_fixed(self):
        self.page('modules/access-control/tech.md', ['technical'],
                  'See [the sample](../../../assets/api/home/absent.json).')
        with self.assertRaisesRegex(ValueError, 'Missing manual asset'):
            builder.copy_pages(self.source, self.target, 'technical', None)

    def test_a_link_into_another_audience_fails(self):
        self.page('modules/access-control/admin.md', ['administrator'])
        self.page('modules/access-control/tech.md', ['technical'], 'See [admin](admin.md).')
        with self.assertRaisesRegex(ValueError, 'Cross-audience page link'):
            builder.copy_pages(self.source, self.target, 'technical', None)

    def test_an_asset_outside_the_documentation_roots_is_refused(self):
        (self.root / 'outside.json').write_text('{}', encoding='utf-8')
        self.page('modules/access-control/tech.md', ['technical'], 'See [it](../../../../outside.json).')
        with self.assertRaisesRegex(ValueError, 'escapes documentation roots'):
            builder.copy_pages(self.source, self.target, 'technical', None)

    def test_html_assets_point_at_built_pages(self):
        self.page('modules/access-control/tech.md', ['technical'], 'Body.')
        diagram = self.docs / 'assets/diagrams/home.html'
        diagram.parent.mkdir(parents=True, exist_ok=True)
        diagram.write_text('<a href="../../en/modules/access-control/tech.md">Page</a>', encoding='utf-8')
        page = self.source / 'modules/access-control/tech.md'
        page.write_text(page.read_text(encoding='utf-8') + '\n[Diagram](../../../assets/diagrams/home.html)\n',
                        encoding='utf-8')
        builder.copy_pages(self.source, self.target, 'technical', None)
        staged = (self.target / 'assets/diagrams/home.html').read_text(encoding='utf-8')
        self.assertIn('tech.html', staged)


if __name__ == '__main__':
    unittest.main()
