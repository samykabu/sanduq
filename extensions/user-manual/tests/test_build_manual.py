"""Portable build_manual: edition staging, asset privacy, theme selection and navigation."""
import importlib.util
import io
import sys
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
        self.assertIn('tech.md', (self.target / 'assets/diagrams/home.html').read_text(encoding='utf-8'))
        builder.copy_pages(self.source, self.root / 'site', 'technical', None, '.html')
        self.assertIn('tech.html', (self.root / 'site/assets/diagrams/home.html').read_text(encoding='utf-8'))



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
        (self.root / 'manual.yml').write_text('languages:\n  required: [en]\nrenderer:\n  kind: mkdocs\n',
                                              encoding='utf-8')
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
        self.assertEqual(('material', {}), builder.resolve_theme({}, Path('.')))

    def test_resolve_theme_refuses_an_uninstalled_theme(self):
        with self.assertRaisesRegex(SystemExit, 'requirements-mkdocs.lock'):
            builder.resolve_theme({'theme': 'no-such-theme'}, Path('.'))

    def test_theme_options_must_be_a_mapping(self):
        with self.assertRaises(SystemExit):
            builder.resolve_theme({'theme': 'readthedocs', 'theme_options': ['x']}, Path('.'))

    def test_a_project_relative_custom_dir_works_from_the_temporary_build_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'theme/overrides').mkdir(parents=True)
            _, options = builder.resolve_theme({'custom_dir': 'theme/overrides'}, root)
            self.assertEqual(str(root / 'theme/overrides'), options['custom_dir'])
            with self.assertRaisesRegex(SystemExit, 'custom_dir not found'):
                builder.resolve_theme({'theme_options': {'custom_dir': 'theme/missing'}}, root)


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


class PdfDocumentTests(unittest.TestCase):
    """mkdocs-to-pdf rebuilds <html> without lang and dir, and fails on themes it has no handler for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'docs/ar').mkdir(parents=True)
        (self.root / 'docs/ar/index.md').write_text('---\ntitle: البداية\naudiences: [end-user]\n---\n# الرئيسية\n',
                                                     encoding='utf-8')
        patcher = mock.patch.object(builder, 'installed_themes', return_value={'material', 'readthedocs'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def build(self, theme):
        manual = {'languages': {'required': ['ar'], 'rtl': ['ar']}, 'renderer': {'kind': 'mkdocs', 'theme': theme}}
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
                                          renderer=None, pdf=True, archive=False)
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
        self.assertEqual([{'البداية': 'index.md'}], seen['config']['nav'], 'the authored title labels the page')

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

    def test_the_brand_reaches_the_cover_and_the_logo(self):
        (self.root / 'theme').mkdir()
        (self.root / 'theme/logo.svg').write_text('<svg/>', encoding='utf-8')
        (self.root / 'theme/brand.yml').write_text(
            'title: Booking Demo\nauthor: Platform team\nlogo: theme/logo.svg\ncolors: {primary: "#1f6f78"}\n',
            encoding='utf-8')
        seen = self.build('material')
        options = seen['config']['plugins'][1]['to-pdf']
        self.assertEqual(('Booking Demo', 'دليل المستخدم', 'Platform team'),
                         (options['cover_title'], options['cover_subtitle'], options['author']))
        self.assertTrue(options['cover_logo'].startswith('file:') and options['cover_logo'].endswith('logo.svg'))
        self.assertIn('assets/stylesheets/brand.css', seen['config']['extra_css'])

    def test_the_projects_own_pdf_templates_replace_the_defaults(self):
        (self.root / 'theme/pdf').mkdir(parents=True)
        (self.root / 'theme/pdf/cover.html').write_text('<article id="doc-cover">Mine</article>', encoding='utf-8')
        self.assertIn('Mine', self.build('material')['cover'])


def edition_root(tmp):
    root = Path(tmp).resolve()
    for language, title in (('en', 'Home'), ('ar', 'الرئيسية')):
        (root / f'docs/{language}/modules/booking').mkdir(parents=True)
        (root / f'docs/{language}/index.md').write_text(
            f'---\ntitle: {title}\naudiences: [end-user]\nmodule: system\n---\n# {title}\n\n'
            '[Book](modules/booking/index.md)\n', encoding='utf-8')
        (root / f'docs/{language}/modules/booking/index.md').write_text(
            '---\naudiences: [end-user]\nmodule: booking\n---\n# Booking\n', encoding='utf-8')
    (root / 'manual.yml').write_text(
        'product_name: Booking Demo\nlanguages:\n  required: [en]\n  optional: [ar]\n  rtl: [ar]\n'
        'modules:\n  - id: booking\n    name: Booking\n', encoding='utf-8')
    return root


def edition_args(language='en', **extra):
    return builder.argparse.Namespace(**{'language': language, 'audience': 'end-user', 'module': None,
                                         'version': 'v1', 'renderer': None, 'pdf': False, 'archive': False, **extra})


class MarkdownRendererTests(unittest.TestCase):
    """The default renderer: the assembled edition is the output, readable on GitHub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = edition_root(self.tmp.name)
        self.manual = builder.yaml.safe_load((self.root / 'manual.yml').read_text(encoding='utf-8'))

    def test_the_edition_is_markdown_with_a_manifest_in_reading_order(self):
        site, archive, pdf = builder.build_edition(edition_args('ar', archive=True), self.root, self.manual)
        self.assertEqual(self.root / 'site/v1/ar/end-user', site)
        self.assertIsNone(pdf)
        manifest = builder.json.loads((site / 'edition.json').read_text(encoding='utf-8'))
        self.assertEqual(['index.md', 'modules/booking/index.md'], manifest['pages'])
        self.assertEqual(('rtl', 'المحتويات', 'Booking Demo - دليل المستخدم'),
                         (manifest['direction'], manifest['toc_title'], manifest['title']))
        page = (site / 'index.md').read_text(encoding='utf-8')
        self.assertIn('(modules/booking/index.md)', page)
        self.assertTrue(page.startswith('# الرئيسية'), 'front matter is source metadata, not output')
        self.assertEqual({'index.md': 'الرئيسية'}, manifest['titles'])
        self.assertEqual(['index.md', {'Modules': [{'Booking': [{'Home': 'modules/booking/index.md'}]}]}],
                         builder.titled_nav(['index.md', {'Modules': [{'Booking': ['modules/booking/index.md']}]}],
                                            {'modules/booking/index.md': 'Home'}))
        metadata = builder.yaml.safe_load((site / 'metadata.yml').read_text(encoding='utf-8'))
        self.assertEqual(('ar', 'rtl', 'Booking Demo'), (metadata['lang'], metadata['dir'], metadata['title']))
        self.assertTrue(archive.is_file())

    def test_pages_nested_below_the_navigation_stay_in_reading_order(self):
        tasks = self.root / 'docs/en/modules/booking/tasks'
        tasks.mkdir()
        (tasks / 'refund.md').write_text('---\naudiences: [end-user]\nmodule: booking\n---\n# Refund\n', encoding='utf-8')
        (self.root / 'docs/en/modules/aaa').mkdir()
        (self.root / 'docs/en/modules/aaa/index.md').write_text('---\naudiences: [end-user]\nmodule: aaa\n---\n# A\n',
                                                               encoding='utf-8')
        site, _, _ = builder.build_edition(edition_args(), self.root, self.manual)
        manifest = builder.json.loads((site / 'edition.json').read_text(encoding='utf-8'))
        self.assertEqual(['index.md', 'modules/booking/index.md', 'modules/booking/tasks/refund.md',
                          'modules/aaa/index.md'], manifest['pages'])

    def test_markdown_is_the_default_and_has_no_pdf(self):
        self.assertEqual('markdown', builder.renderer_settings({})['kind'])
        with self.assertRaisesRegex(SystemExit, 'renderer.kind: mkdocs'):
            builder.build_edition(edition_args(pdf=True), self.root, self.manual)
        with self.assertRaisesRegex(SystemExit, 'renderer.kind must be one of'):
            builder.renderer_settings({'renderer': {'kind': 'sphinx'}})

    def test_a_manual_from_1x_keeps_its_mkdocs_site_and_is_told_to_say_so(self):
        legacy = {'renderer': {'primary': 'mkdocs-material', 'theme': 'readthedocs', 'theme_options': {}}}
        self.assertEqual('mkdocs', builder.renderer_settings(legacy)['kind'])
        self.assertEqual('markdown', builder.renderer_settings({'renderer': {'kind': 'markdown', 'theme': 'x'}})['kind'])
        self.assertEqual('markdown', builder.renderer_settings({'renderer': {}})['kind'])
        (self.root / 'manual.yml').write_text('renderer:\n  theme: material\n', encoding='utf-8')
        argv = ['build_manual.py', '--root', str(self.root), '--print-renderer']
        with mock.patch('sys.argv', argv), mock.patch('sys.stdout', new_callable=io.StringIO) as out, \
                mock.patch('sys.stderr', new_callable=io.StringIO) as err:
            builder.main()
        self.assertEqual('mkdocs', out.getvalue().strip())
        self.assertIn("add 'kind: mkdocs'", err.getvalue())

    def test_print_renderer_reports_the_selected_kind(self):
        argv = ['build_manual.py', '--root', str(self.root), '--print-renderer']
        with mock.patch('sys.argv', argv), mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            builder.main()
        self.assertEqual('markdown', out.getvalue().strip())


RECORDER = (
    'import json, os, sys\n'
    'json.dump({"cwd": os.getcwd(), "args": sys.argv[2:]}, open(os.path.join(sys.argv[1], "call.json"), "w"))\n'
)


class CommandRendererTests(unittest.TestCase):
    """renderer.kind: command runs the project's own tool on the assembled edition."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = edition_root(self.tmp.name)

    def manual(self, command):
        return {**builder.yaml.safe_load((self.root / 'manual.yml').read_text(encoding='utf-8')),
                'renderer': {'kind': 'command', 'command': command}}

    def test_placeholders_and_pages_reach_the_command_which_runs_from_the_manual_root(self):
        command = [sys.executable, '-c', RECORDER, '{output}', '{pages}', '--lang={language}', '{metadata}']
        site, _, _ = builder.build_edition(edition_args(), self.root, self.manual(command))
        call = builder.json.loads((site / 'call.json').read_text(encoding='utf-8'))
        self.assertEqual(str(self.root), call['cwd'])
        self.assertEqual(['index.md', 'modules/booking/index.md'],
                         [Path(arg).as_posix().split('/edition/', 1)[1] for arg in call['args'][:2]])
        self.assertEqual('--lang=en', call['args'][2])
        self.assertTrue(call['args'][3].endswith('metadata.yml'))

    def test_a_string_command_is_split_like_a_shell(self):
        self.assertEqual(['pandoc', '-f', 'gfm+rebase_relative_paths', '/e/a.md', '/e/b.md', '-o', '/out/My Manual.docx'],
                         builder.command_argv('pandoc -f gfm+rebase_relative_paths {pages} -o "{output}/My Manual.docx"',
                                              {'output': '/out'}, ['/e/a.md', '/e/b.md']))

    def test_pandoc_reads_github_markdown_with_page_relative_images_unless_told_otherwise(self):
        self.assertEqual(['pandoc', '--from=gfm+rebase_relative_paths', '/e/a.md', '-o', '/out/m.docx'],
                         builder.command_argv('pandoc {pages} -o {output}/m.docx', {'output': '/out'}, ['/e/a.md']))
        self.assertEqual(['C:/tools/pandoc.exe', '--from=gfm+rebase_relative_paths', '/e/a.md'],
                         builder.command_argv(['C:/tools/pandoc.exe', '{pages}'], {}, ['/e/a.md']))
        for own in ('-f markdown', '--from=commonmark', '-fgfm', '-r gfm'):
            self.assertNotIn('--from=gfm+rebase_relative_paths',
                             builder.command_argv(f'pandoc {own} {{pages}}', {}, ['/e/a.md']), own)
        self.assertEqual(['quarto', 'render'], builder.command_argv('quarto render', {}, []))

    def test_a_failing_silent_or_missing_command_stops_the_build(self):
        failing = [sys.executable, '-c', 'import sys; print("template missing"); sys.exit(3)']
        with mock.patch('sys.stderr', new_callable=io.StringIO) as err, self.assertRaises(SystemExit) as stop:
            builder.build_edition(edition_args(), self.root, self.manual(failing))
        self.assertEqual(3, stop.exception.code)
        self.assertIn('template missing', err.getvalue())
        with self.assertRaisesRegex(SystemExit, 'wrote nothing'):
            builder.build_edition(edition_args(), self.root, self.manual([sys.executable, '-c', 'pass']))
        with self.assertRaisesRegex(SystemExit, 'command not found'):
            builder.build_edition(edition_args(), self.root, self.manual(['no-such-renderer-tool']))
        with self.assertRaisesRegex(SystemExit, 'non-empty string or list'):
            builder.build_edition(edition_args(), self.root, self.manual(None))


class GitHubSyntaxTests(unittest.TestCase):
    """Pages use GitHub's own syntax; the MkDocs renderer translates it."""

    def test_alerts_become_admonitions_titled_in_the_editions_language(self):
        text = '> [!WARNING]\n> Back up first.\n>\n> Then restore.\n\nAfter.\n'
        self.assertEqual('!!! warning "Warning"\n    Back up first.\n\n    Then restore.\n\n\nAfter.\n',
                         builder.mkdocs_markdown(text, 'en'))
        self.assertIn('!!! note "ملاحظة"', builder.mkdocs_markdown('> [!NOTE]\n> سجّل الدخول.\n', 'ar'))

    def test_details_blocks_render_their_markdown(self):
        self.assertEqual('<details markdown="1">\n<summary>Web</summary>\n',
                         builder.mkdocs_markdown('<details>\n<summary>Web</summary>\n', 'en'))
        self.assertEqual('<details markdown="1">', builder.mkdocs_markdown('<details markdown="1">', 'en'))


class LinkFormTests(unittest.TestCase):
    """Titled links, <angle-bracketed> targets and reference definitions are staged like plain links."""

    def test_every_link_form_is_rewritten_and_its_asset_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / 'docs/en'
            (root / 'docs/assets').mkdir(parents=True)
            for name in ('a.png', 'b c.png', 'd.json'):
                (root / 'docs/assets' / name).write_bytes(b'x')
            source.mkdir(parents=True)
            (source / 'index.md').write_text(
                '---\naudiences: [end-user]\n---\n![A](../assets/a.png "Shot")\n![B](<../assets/b c.png>)\n'
                '[data][d]\n\n[d]: ../assets/d.json "Sample"\n[^1]: Explanation\n', encoding='utf-8')
            builder.copy_pages(source, root / 'out', 'end-user', None)
            staged = (root / 'out/index.md').read_text(encoding='utf-8')
            self.assertIn('![A](assets/a.png "Shot")', staged)
            self.assertIn('![B](<assets/b c.png>)', staged)
            self.assertIn('[d]: assets/d.json "Sample"', staged)
            self.assertEqual({'a.png', 'b c.png', 'd.json'}, {p.name for p in (root / 'out/assets').iterdir()})


class FencedCodeTests(unittest.TestCase):
    """Code examples are never links or syntax to translate."""

    def test_a_code_example_that_looks_like_a_link_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / 'docs/en'
            source.mkdir(parents=True)
            body = ('---\naudiences: [technical]\n---\n```js\nconst routes = {\n  [region]: endpoint,\n};\n'
                    '![x](gone.png)\n```\n\n- Step:\n  ~~~text\n  [id]: also-gone.md\n  ~~~\n')
            (source / 'index.md').write_text(body, encoding='utf-8')
            builder.copy_pages(source, root / 'out', 'technical', None)
            self.assertEqual(body.split('---\n', 2)[2], (root / 'out/index.md').read_text(encoding='utf-8'))

    def test_list_fences_and_inline_code_spans_do_not_hide_the_rest_of_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / 'docs/en'
            (root / 'docs/assets').mkdir(parents=True)
            (root / 'docs/assets/screen.png').write_bytes(b'x')
            source.mkdir(parents=True)
            (source / 'index.md').write_text(
                '---\naudiences: [end-user]\n---\n- ```text\n  code\n  ```\n\n```example``` is a span.\n\n'
                '![Screen](../assets/screen.png)\n', encoding='utf-8')
            builder.copy_pages(source, root / 'out', 'end-user', None)
            self.assertIn('![Screen](assets/screen.png)', (root / 'out/index.md').read_text(encoding='utf-8'))
            unclosed = '```\nnever closed\n[x]: y\n'
            self.assertEqual([(0, len(unclosed))], builder.code_blocks(unclosed), 'CommonMark runs it to the page end')
            example = '````markdown\n- ```\n````\n'
            self.assertEqual([(0, len(example))], builder.code_blocks(example + '\nprose\n'),
                             'a list marker before backticks inside code does not close the block')

    def test_indented_code_and_a_list_items_unclosed_fence_end_where_markdown_ends_them(self):
        page = ('    ```text\n\n![Screen](../assets/screen.png)\n\n- step\n  ```\n  [x]: y\n\n'
                '![Again](../assets/screen.png)\n\n```python\nprint(1)\n```\n')
        blocks = builder.code_blocks(page)
        self.assertEqual(3, len(blocks), blocks)
        covered = ''.join(page[start:end] for start, end in blocks)
        self.assertNotIn('![Screen]', covered)
        self.assertNotIn('![Again]', covered)
        self.assertIn('[x]: y', covered)

    def test_a_longer_closing_fence_ends_the_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / 'docs/en'
            (root / 'docs/assets').mkdir(parents=True)
            (root / 'docs/assets/screen.png').write_bytes(b'x')
            source.mkdir(parents=True)
            (source / 'index.md').write_text('---\naudiences: [end-user]\n---\n```\ncode\n````\n\n'
                                             '![Screen](../assets/screen.png)\n', encoding='utf-8')
            builder.copy_pages(source, root / 'out', 'end-user', None)
            self.assertIn('![Screen](assets/screen.png)', (root / 'out/index.md').read_text(encoding='utf-8'))
            self.assertTrue((root / 'out/assets/screen.png').is_file())

    def test_an_alert_containing_code_is_converted_whole(self):
        text = '> [!NOTE]\n> Run:\n> ```python\n> print(1)\n> ```\n> Then <details> opens.\n'
        self.assertEqual('!!! note "Note"\n    Run:\n    ```python\n    print(1)\n    ```\n'
                         '    Then <details markdown="1"> opens.\n\n', builder.mkdocs_markdown(text, 'en'))

    def test_html_and_svg_assets_keep_every_link_whatever_their_indentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / 'docs/en'
            (root / 'docs/assets').mkdir(parents=True)
            (root / 'docs/assets/screen.png').write_bytes(b'x')
            (root / 'docs/assets/flow.svg').write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">\n\n    <image href="screen.png"/>\n</svg>\n', encoding='utf-8')
            source.mkdir(parents=True)
            (source / 'index.md').write_text('---\naudiences: [end-user]\n---\n![Flow](../assets/flow.svg)\n',
                                             encoding='utf-8')
            builder.copy_pages(source, root / 'out', 'end-user', None)
            self.assertTrue((root / 'out/assets/screen.png').is_file())

    def test_mkdocs_translation_skips_code_blocks(self):
        text = '```markdown\n> [!NOTE]\n> Example.\n<details>\n```\n> [!TIP]\n> Real.\n'
        converted = builder.mkdocs_markdown(text, 'en')
        self.assertTrue(converted.startswith('```markdown\n> [!NOTE]\n> Example.\n<details>\n```\n'), converted)
        self.assertIn('!!! tip "Tip"', converted)


class BrandTests(unittest.TestCase):
    def test_the_title_defaults_to_the_product_and_a_missing_logo_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual({'title': 'Demo'}, builder.load_brand(root, {'product_name': 'Demo'}))
            (root / 'theme').mkdir()
            (root / 'theme/brand.yml').write_text('title: null\nauthor: Team\nlogo: theme/gone.svg\n', encoding='utf-8')
            with self.assertRaisesRegex(SystemExit, 'brand logo not found'):
                builder.load_brand(root, {'product_name': 'Demo'})


if __name__ == '__main__':
    unittest.main()
