#!/usr/bin/env python3
"""Build the authored sample with the real extension builder and capture browser screenshots."""
import argparse
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

SOURCE = Path(__file__).resolve().parent
REPO = SOURCE.parents[2]
VARIANTS = {
    'material-light': ('material', {'palette': {'scheme': 'default', 'primary': 'indigo'}}),
    'material-dark': ('material', {'palette': {'scheme': 'slate', 'primary': 'indigo'}}),
    'readthedocs': ('readthedocs', {}),
    'mkdocs': ('mkdocs', {}),
    'booking-brand': ('material', {'palette': {'scheme': 'default'}}),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable, help='Python with the pinned manual renderer requirements')
    parser.add_argument('--output', type=Path, default=REPO / 'dist' / 'booking-manual-gallery')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((REPO / 'dist').resolve()) or output.exists():
        raise SystemExit('Choose a new output directory under this repository\'s dist/')
    output.mkdir(parents=True)
    screenshots = REPO / 'docs' / 'assets' / 'manual-gallery'
    screenshots.mkdir(parents=True, exist_ok=True)
    for variant, (name, options) in VARIANTS.items():
        root = output / variant / 'User-Manual'
        shutil.copytree(SOURCE, root, ignore=shutil.ignore_patterns('build_gallery.py', '__pycache__', 'site', '.build-*'))
        config = yaml.safe_load((root / 'manual.yml').read_text(encoding='utf-8'))
        config['renderer'].update(theme=name, theme_options=options)
        (root / 'manual.yml').write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
        if variant == 'booking-brand':
            with (root / 'theme' / 'extra.css').open('a', encoding='utf-8') as css:
                css.write('\n:root{--manual-primary:#172033;--manual-accent:#875d09;}\n.md-header{border-bottom:4px solid #caa344;}\n')
        for script, flags in [('audit_manual.py', []), ('build_manual.py', ['--audience', 'end-user', '--language', 'en', '--version', 'v3.0.0'])]:
            subprocess.run([args.python, str(REPO / 'extensions' / 'user-manual' / 'scripts' / script), '--root', str(root), *flags], check=True)
    handler = partial(SimpleHTTPRequestHandler, directory=str(output))
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
                for variant in VARIANTS:
                    url = f'http://127.0.0.1:{server.server_port}/{variant}/User-Manual/site/v3.0.0/en/end-user/index.html'
                    page.goto(url, wait_until='networkidle')
                    page.evaluate('document.fonts.ready')
                    assert page.locator('h1').inner_text() == 'Booking example'
                    image = page.locator('img[alt="Refund approval process"]')
                    assert image.evaluate('(img) => img.complete && img.naturalWidth > 0')
                    for module in ('booking', 'payments', 'operations'):
                        assert page.locator(f'a[href="modules/{module}/index.html"]').count() >= 1
                    page.screenshot(path=str(screenshots / f'{variant}.png'), full_page=True)
                    print(f'{variant}: actual builder output and embedded diagram verified')
                browser.close()
        finally:
            server.shutdown()
            worker.join(timeout=5)


if __name__ == '__main__':
    main()
