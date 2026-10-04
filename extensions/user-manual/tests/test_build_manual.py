"""Edition staging: which pages an audience receives, and which assets follow them."""
import importlib.util
import tempfile
import unittest
from unittest import mock
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


class ThemeTests(unittest.TestCase):
    """The renderer.theme selection: config per theme, locales and RTL styling.

    The MkDocs lookups are stubbed so the suite runs where MkDocs is not
    installed (the CI regression job installs only the test requirements).
    """

    def setUp(self):
        locales = {'readthedocs': {'en', 'fr'}, 'mkdocs': {'en', 'fr'}}
        for name, value in (('installed_themes', lambda: {'material', 'readthedocs', 'mkdocs'}),
                            ('theme_locales', lambda theme: locales.get(theme))):
            patcher = mock.patch.object(builder, name, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_material_keeps_its_features_and_palette(self):
        config = builder.theme_config('material', 'ar')
        self.assertEqual('material', config['name'])
        self.assertEqual('ar', config['language'])
        self.assertIn('navigation.tabs', config['features'])
        self.assertEqual(2, len(config['palette']))

    def test_readthedocs_sets_only_a_locale_the_theme_ships(self):
        self.assertEqual('fr', builder.theme_config('readthedocs', 'fr').get('locale'))
        self.assertNotIn('locale', builder.theme_config('readthedocs', 'ar'))
        self.assertEqual('readthedocs', builder.theme_config('readthedocs', 'en')['name'])

    def test_theme_options_override_defaults_but_not_the_name(self):
        config = builder.theme_config('readthedocs', 'en', {'navigation_depth': 2, 'name': 'other'})
        self.assertEqual(2, config['navigation_depth'])
        self.assertEqual('readthedocs', config['name'])

    def test_unknown_theme_options_pass_through_for_other_themes(self):
        config = builder.theme_config('mkdocs', 'en', {'color_mode': 'dark'})
        self.assertEqual({'name': 'mkdocs', 'locale': 'en', 'color_mode': 'dark'}, config)

    def test_rtl_stylesheet_per_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp)
            self.assertIsNone(builder.rtl_stylesheet(theme_dir, 'material'))
            self.assertEqual('rtl-readthedocs.css', builder.rtl_stylesheet(theme_dir, 'readthedocs'))
            self.assertEqual('rtl-generic.css', builder.rtl_stylesheet(theme_dir, 'mkdocs'))
            (theme_dir / 'rtl-mkdocs.css').write_text('body{}', encoding='utf-8')
            self.assertEqual('rtl-mkdocs.css', builder.rtl_stylesheet(theme_dir, 'mkdocs'))

    def test_project_stylesheet_overrides_the_shipped_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            theme_dir = Path(tmp)
            self.assertEqual(builder.SCAFFOLD_THEME / 'rtl-generic.css',
                             builder.stylesheet_source(theme_dir, 'rtl-generic.css'))
            (theme_dir / 'rtl-generic.css').write_text('body{}', encoding='utf-8')
            self.assertEqual(theme_dir / 'rtl-generic.css', builder.stylesheet_source(theme_dir, 'rtl-generic.css'))

    def test_resolve_theme_defaults_to_material(self):
        self.assertEqual(('material', {}), builder.resolve_theme({}, 'material'))

    def test_resolve_theme_refuses_an_uninstalled_theme(self):
        with self.assertRaises(SystemExit):
            builder.resolve_theme({'renderer': {'theme': 'no-such-theme'}}, 'material')

    def test_zensical_only_checks_material(self):
        with self.assertRaises(SystemExit):
            builder.resolve_theme({'renderer': {'theme': 'readthedocs'}}, 'zensical')

    def test_theme_options_must_be_a_mapping(self):
        with self.assertRaises(SystemExit):
            builder.resolve_theme({'renderer': {'theme': 'readthedocs', 'theme_options': ['x']}}, 'material')


class NavTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.docs = Path(self.tmp.name)
        for rel in ('index.md', 'modules/payments/technical.md', 'modules/payments/index.md',
                    'modules/payments/user-guide.md', 'modules/accounts/index.md', 'modules/extra/index.md'):
            (self.docs / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.docs / rel).write_text('# x\n', encoding='utf-8')
        self.manual = {'modules': [
            {'id': 'payments', 'name': 'Payments', 'translations': {'ar': {'name': 'المدفوعات'}}},
            {'id': 'accounts', 'name': 'Accounts'},
        ]}

    def test_modules_follow_manual_order_with_translated_names(self):
        nav = builder.build_nav(self.docs, self.manual, 'ar')
        self.assertEqual('index.md', nav[0])
        sections = nav[1]['الوحدات']
        self.assertEqual(['المدفوعات', 'Accounts', 'Extra'], [next(iter(s)) for s in sections])

    def test_pages_inside_a_module_are_in_reading_order(self):
        sections = builder.build_nav(self.docs, self.manual, 'en')[1]['Modules']
        self.assertEqual(['modules/payments/index.md', 'modules/payments/user-guide.md',
                          'modules/payments/technical.md'], sections[0]['Payments'])
