"""Portable build_manual: edition staging, asset privacy, theme selection and navigation."""
import importlib.util
import io
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

    def test_one_audiences_assets_do_not_leak_into_another_edition(self):
        shot = self.source / 'modules/access-control/admin-console.png'
        shot.write_bytes(b'png')
        (self.docs / 'assets/api/home/refunds.json').write_text('{}', encoding='utf-8')
        self.page('modules/access-control/admin.md', ['administrator'],
                  '![Console](admin-console.png) [Refunds](../../../assets/api/home/refunds.json)')
        self.page('modules/access-control/tech.md', ['technical'],
                  'See [the sample](../../../assets/api/home/projects.json).')
        builder.copy_pages(self.source, self.target, 'technical', None)
        staged = {p.relative_to(self.target).as_posix() for p in self.target.rglob('*') if p.is_file()}
        self.assertEqual({'modules/access-control/tech.md', 'assets/api/home/projects.json'}, staged)

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



class AllEditionsTests(unittest.TestCase):
    """`--all` builds the three audiences for each manual.yml language whose docs/<lang>/ directory exists."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'docs/en').mkdir(parents=True)
        (self.root / 'manual.yml').write_text('languages:\n  required: [en]\n  optional: [ar]\n', encoding='utf-8')

    def run_all(self, *extra):
        calls = []

        def fake(args, root, manual):
            calls.append(args)
            return root / 'site' / args.version / args.language / args.audience, None, root / 'x.pdf' if args.pdf else None

        argv = ['build_manual.py', '--root', str(self.root), '--all', *extra]
        with mock.patch.object(builder, 'build_edition', side_effect=fake), mock.patch('sys.argv', argv), \
                mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            builder.main()
        return calls, out.getvalue().splitlines()

    def test_builds_only_languages_that_have_a_directory(self):
        calls, lines = self.run_all()
        self.assertEqual([(c.audience, c.language) for c in calls],
                         [('end-user', 'en'), ('administrator', 'en'), ('technical', 'en')])
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('end-user en: '), lines[0])

    def test_passes_version_archive_and_pdf_through_to_every_edition(self):
        (self.root / 'docs/ar').mkdir()
        calls, lines = self.run_all('--version', 'v1.2', '--archive', '--pdf')
        self.assertEqual(len(calls), 6)
        self.assertEqual({(c.version, c.archive, c.pdf) for c in calls}, {('v1.2', True, True)})
        self.assertEqual([c.language for c in calls], ['en'] * 3 + ['ar'] * 3)
        self.assertTrue(all(line.endswith('x.pdf') for line in lines), lines)

    def test_all_refuses_a_single_edition_flag_and_an_empty_language_set(self):
        with self.assertRaises(SystemExit):
            self.run_all('--language', 'en')
        (self.root / 'manual.yml').write_text('languages:\n  required: [fr]\n', encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'no language directory'):
            self.run_all()


class BuildOutputTests(unittest.TestCase):
    """The renderer's banner stays out of the caller's output; its error still shows when the build fails."""

    BANNER = 'INFO    -  MkDocs 2.0 is coming, Material for MkDocs banner\nINFO    -  Cleaning site directory'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'docs/en').mkdir(parents=True)
        (self.root / 'docs/en/index.md').write_text('---\naudiences: [end-user, administrator, technical]\n---\n# Home\n',
                                                     encoding='utf-8')
        (self.root / 'manual.yml').write_text('languages:\n  required: [en]\n', encoding='utf-8')
        patcher = mock.patch.object(builder, 'installed_themes', return_value={'material'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, returncode, log):
        def fake_run(command, cwd, check, **kwargs):
            (Path(cwd) / 'site').mkdir()
            if kwargs.get('stdout') is None:  # an inherited stdout writes straight into the caller's output
                print(log)
                log_out = None
            else:
                log_out = log
            return builder.subprocess.CompletedProcess(command, returncode, stdout=log_out)

        argv = ['build_manual.py', '--root', str(self.root), '--all']
        with mock.patch.object(builder.subprocess, 'run', side_effect=fake_run), mock.patch('sys.argv', argv), \
                mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            try:
                builder.main()
            except SystemExit as exit_:
                return out.getvalue(), err.getvalue(), exit_.code
        return out.getvalue(), err.getvalue(), 0

    def test_a_successful_build_prints_one_line_per_edition(self):
        out, err, code = self.build(0, self.BANNER)
        self.assertEqual(0, code)
        self.assertEqual(['end-user en', 'administrator en', 'technical en'],
                         [line.split(':')[0] for line in out.splitlines()])
        self.assertNotIn('MkDocs 2.0', out + err)

    def test_a_failing_build_shows_the_renderer_error(self):
        out, err, code = self.build(1, self.BANNER + "\nERROR   -  Doc file 'index.md' contains a link to 'gone.md'")
        self.assertEqual(1, code)
        self.assertIn("contains a link to 'gone.md'", err)
        self.assertIn('end-user-en', err)
        self.assertEqual('', out)


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


if __name__ == '__main__':
    unittest.main()


class PdfDocumentTests(unittest.TestCase):
    """mkdocs-to-pdf rebuilds <html> without lang and dir, and fails on themes it has no handler for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'docs/ar').mkdir(parents=True)
        (self.root / 'docs/ar/index.md').write_text('---\naudiences: [end-user]\n---\n# الرئيسية\n', encoding='utf-8')
        patcher = mock.patch.object(builder, 'installed_themes', return_value={'material', 'readthedocs'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, theme):
        manual = {'languages': {'required': ['ar'], 'rtl': ['ar']}, 'renderer': {'theme': theme}}
        seen = {}

        def fake_run(command, cwd=None, check=False, **kwargs):
            if cwd:  # the renderer, not the WeasyPrint preflight
                build = Path(cwd)
                seen.update({p.name: p.read_text(encoding='utf-8') for p in build.glob('pdf_*.py')})
                seen['config'] = builder.yaml.safe_load((build / 'mkdocs.yml').read_text(encoding='utf-8'))
                seen['cover'] = (build / 'pdf_templates/cover.html').read_text(encoding='utf-8')
                (build / 'site').mkdir()
                (build / 'site/end-user-ar.pdf').write_bytes(b'%PDF')
            return builder.subprocess.CompletedProcess(command, 0, stdout='')

        args = builder.argparse.Namespace(language='ar', audience='end-user', module=None, version='v1',
                                          renderer='material', pdf=True, archive=False)
        # theme_config reads MkDocs' theme locales; these tests need no MkDocs.
        with mock.patch.object(builder.subprocess, 'run', side_effect=fake_run), \
                mock.patch.object(builder, 'theme_config', side_effect=lambda name, *_: {'name': name}):
            builder.build_edition(args, self.root, manual)
        return seen

    def test_the_pdf_keeps_the_edition_language_and_direction(self):
        seen = self.build('material')
        namespace = {}
        exec(seen['pdf_event_hook.py'], namespace)
        html = type('Html', (dict,), {})()
        namespace['pre_pdf_render'](type('Soup', (), {'html': html})(), None)
        self.assertEqual({'lang': 'ar', 'dir': 'rtl'}, dict(html))
        self.assertNotIn('pdf_theme_handler.py', seen)
        self.assertNotIn('theme_handler_path', seen['config']['plugins'][1]['to-pdf'])

    def test_the_cover_omits_unset_fields_and_the_contents_heading_follows_the_language(self):
        seen = self.build('material')
        options = seen['config']['plugins'][1]['to-pdf']
        self.assertEqual('المحتويات', options['toc_title'])
        self.assertEqual('pdf_templates', options['custom_template_path'])
        try:
            import jinja2
        except ImportError:
            self.skipTest('jinja2 is not installed')
        page = jinja2.Template(seen['cover']).render(cover_title='دليل', cover_subtitle=None, author=None,
                                                    copyright=None)
        self.assertIn('<h1>دليل</h1>', page)
        self.assertNotIn('None', page)
        self.assertIn('<p id="author">Team</p>', jinja2.Template(seen['cover']).render(cover_title='x', author='Team'))

    def test_a_theme_without_a_renderer_handler_gets_one(self):
        seen = self.build('readthedocs')
        self.assertEqual('pdf_theme_handler.py', seen['config']['plugins'][1]['to-pdf']['theme_handler_path'])
        namespace = {}
        exec(seen['pdf_theme_handler.py'], namespace)
        self.assertEqual('<p>x</p>', namespace['inject_link']('<p>x</p>', 'a.pdf', None, None, None))
        self.assertIsNone(namespace['get_stylesheet'](False))
