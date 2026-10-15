"""Regenerate docs/assets/progress-*.png from projection-sample.json (needs Playwright + a Chromium)."""
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import test_ui_browser as t  # noqa: E402
from sanduq_progress import theme  # noqa: E402

OUT = HERE.parent / "docs" / "assets"


def main():
    t.setUpModule()
    if t.SKIP:
        sys.exit(t.SKIP)
    view = Path(tempfile.mkdtemp())
    for f in ("index.html", "base.css", "blocks.js"):
        shutil.copy(t.UI / f, view / f)
    theme.write_assets(view, theme.resolve_doc({}))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, scheme, width in (("progress-light", "light", 1280), ("progress-dark", "dark", 1280), ("progress-narrow", "light", 360)):
        t.write_data(view, t.fresh(t.load("projection-sample.json")))
        ctx = t.BROWSER.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
        page = ctx.new_page()
        page.goto((view / "index.html").as_uri())
        page.wait_for_selector("h1")
        page.screenshot(path=str(OUT / (name + ".png")), full_page=True)
        ctx.close()
    t.tearDownModule()
    shutil.rmtree(view, ignore_errors=True)


if __name__ == "__main__":
    main()
