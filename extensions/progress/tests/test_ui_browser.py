import copy
import datetime
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent / "assets" / "ui"
FIX = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))
import helpers  # noqa: E402
from sanduq_progress import model, statusline, theme  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

PW = None
BROWSER = None
SKIP = "playwright/chromium unavailable"
# The poller ticks every 3 s; on a loaded machine (parallel suites, CI) Chromium throttles timers, so a 6 s wait flaked.
UPDATE_WAIT = 30000


def setUpModule():
    global PW, BROWSER, SKIP
    if sync_playwright is None:
        return
    try:
        PW = sync_playwright().start()
        for kw in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
            try:
                BROWSER = PW.chromium.launch(**kw)
                SKIP = ""
                break
            except Exception as exc:
                SKIP = "playwright/chromium unavailable: " + str(exc).splitlines()[0][:80]
        if BROWSER is None:
            PW.stop()
            PW = None
            return
    except Exception as exc:
        SKIP = "playwright failed to start: " + str(exc).splitlines()[0][:80]


def tearDownModule():
    if BROWSER:
        BROWSER.close()
    if PW:
        PW.stop()


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def now_iso(delta=0):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=delta)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh(proj, rev=None, **over):
    p = copy.deepcopy(proj)
    p["generated_at"] = now_iso()
    if rev is not None:
        p["rev"] = rev
    p.update(over)
    return p


def write_data(view, proj):
    # write via replace so the browser never reads a torn file
    tmp = view / "data.js.tmp"
    tmp.write_text("window.__SANDUQ_PROGRESS__ = " + json.dumps(proj, ensure_ascii=False) + ";\n", encoding="utf-8")
    tmp.replace(view / "data.js")


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class BrowserTest(unittest.TestCase):
    scheme = None

    def setUp(self):
        if SKIP:
            self.skipTest(SKIP)
        self.view_tmp = tempfile.TemporaryDirectory()
        self.view = Path(self.view_tmp.name)
        for f in ("index.html", "base.css", "blocks.js"):
            shutil.copy(UI / f, self.view / f)
        theme.write_assets(self.view, theme.resolve_doc({}))
        self.bctx = BROWSER.new_context(viewport={"width": 1280, "height": 900}, color_scheme=self.scheme)
        self.page = self.bctx.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))

    def tearDown(self):
        if getattr(self, "bctx", None):
            self.bctx.close()
            helpers.remove_tree(self.view_tmp)

    def open(self, proj=None, **kw):
        write_data(self.view, proj if proj is not None else fresh(load("projection-sample.json")))
        self.page.goto((self.view / "index.html").as_uri() + kw.get("hash", ""))
        self.page.wait_for_selector("h1")

    def text(self, sel):
        return self.page.inner_text(sel)

    def wait_text(self, sel, needle, timeout=UPDATE_WAIT):
        self.page.wait_for_function("([s,n])=>{const e=document.querySelector(s);return e&&e.textContent.includes(n)}",
                                    arg=[sel, needle], timeout=timeout)


class RealProjectionTests(helpers.Project, BrowserTest):
    """The UI rendering a projection produced by the real builder (model.py) from real producer files, so unit and
    shape mismatches between the two cannot hide behind hand-written fixtures."""

    def setUp(self):
        helpers.Project.setUp(self)
        BrowserTest.setUp(self)

    def real_projection(self):
        self.init(debounce_seconds=0)
        self.bind()
        stat = json.loads(helpers.fixture("claude_statusline.json", CWD=self.root.as_posix()))
        statusline.record(json.dumps(stat), self.root, datetime.datetime(2026, 10, 15, 12, 0, 5, tzinfo=datetime.timezone.utc))
        folder = self.feature_dir / "workflow"
        folder.mkdir()
        (folder / "delegations.json").write_text(json.dumps({"attempts": [{
            "identity": "specs/001-demo/T002", "run_id": "run-1", "requested_harness": "codex", "requested_model": "m",
            "actual_model": "gpt-real", "actual_model_evidence": "driver-result", "status": "successful",
            "started_at": "2026-10-15T10:00:00Z", "ended_at": "2026-10-15T11:00:00Z"}]}), encoding="utf-8")
        (folder / "decisions.json").write_text(json.dumps({"version": 1, "decisions": [{
            "id": "SD1", "mode": "multiple", "options": ["Alpha", "Beta", "Gamma"], "status": "answered", "option": None,
            "selected": ["A", "C"], "answers": [{"option": "A", "updated_at": "2026-10-15T09:00:00Z"}]}]}), encoding="utf-8")
        built = model.build(self.ctx, datetime.datetime(2026, 10, 15, 12, 30, tzinfo=datetime.timezone.utc), 1, {})
        return fresh(built)

    def test_durations_selections_and_unknowns_render_from_real_output(self):
        proj = self.real_projection()
        self.assertEqual(proj["orchestrator"]["elapsed"]["value"], 45)  # seconds, not milliseconds
        self.open(proj)
        orch = self.text("#b-orchestrator")
        self.assertIn("45s", orch)
        self.assertIn("82,000", orch)  # current-usage tokens from the statusline fixture
        lanes = self.text("#b-lanes")
        self.assertIn("1h 0m", lanes)  # a one-hour attempt, lane elapsed and the attempt line
        self.assertEqual(self.page.locator("#b-lanes details li").first.text_content().count("1h 0m"), 1)
        self.assertIn("gpt-real", lanes)
        self.assertIn("Selected Alpha, Gamma", self.text("#b-decisions"))
        self.assertEqual(self.page.locator("#b-decisions .sel").count(), 2)
        self.assertEqual(self.errors, [])


class SampleTests(BrowserTest):
    def test_every_block_renders(self):
        self.open()
        p = self.page
        self.assertIn("Add dependencies when creating a task", self.text("h1"))
        self.assertEqual(p.get_attribute("a[href*='issues/624']", "href"), "https://github.com/example/repo/issues/624")
        hdr = self.text("header")
        for needle in ("Branch", "execute", "3 / 9 (33%)", "Lanes active", "Decisions pending"):
            self.assertIn(needle, hdr)
        self.assertEqual(p.get_attribute("[role=progressbar]", "aria-valuenow"), "3")
        orch = self.text("#b-orchestrator")
        for needle in ("claude-opus-5-5", "high", "41.2%", "82,400", "2h 27m", "52m 0s", "exact", "partial"):
            self.assertIn(needle, orch.lower())
        self.assertEqual(p.get_attribute("#b-orchestrator [role=meter]", "aria-valuenow"), "41.2")
        self.assertEqual(p.locator("#b-lanes th[scope=col]").count(), 9)
        self.assertEqual(p.locator("#b-lanes tbody tr").count(), 3)
        lanes = self.text("#b-lanes")
        for needle in ("requested codex gpt-6.1-sol", "observed", "claude-sonnet-5-5", "done", "active", "blocked", "2 attempts", "unknown"):
            self.assertIn(needle, lanes)
        self.assertEqual(p.locator("#b-lanes details").count(), 3)
        boards = self.text("#b-boards")
        for needle in ("Active", "Waiting", "Blocked", "Done", "T004", "Dependency picker on the create-task form",
                       "blocked by L2", "blocked by D2", "blocked by T004", "blocked by external: staging database refresh", "Unassigned", "T009"):
            self.assertIn(needle, boards)
        dec = self.text("#b-decisions")
        self.assertLess(dec.index("D2"), dec.index("D1"))  # pending first
        for needle in ("removable after the dependent task starts", "Selected 25 by user", "evidence"):
            self.assertIn(needle, dec)
        self.assertEqual(p.get_attribute("#b-decisions a", "href"), "https://github.com/example/repo/issues/624#issuecomment-1")
        bl = self.text("#b-blockers")
        for needle in ("B1", "T006", "lane: L2", "B2", "decision: D2"):
            self.assertIn(needle, bl)
        self.assertEqual(p.locator("#b-events li").count(), 6)
        self.assertIn("D1 made: 25 by user", self.text("#b-events"))
        self.assertEqual(self.errors, [])
        self.assertEqual(p.inner_text("#banners").strip(), "")

    def test_events_capped_at_30(self):
        proj = fresh(load("projection-sample.json"))
        proj["events"] = [{"at": now_iso(-i), "kind": "note", "text": "e%d" % i} for i in range(45)]
        self.open(proj)
        self.assertEqual(self.page.locator("#b-events li").count(), 30)

    def test_theme_layout_order_and_hidden(self):
        theme.write_assets(self.view, theme.resolve_doc({"blocks": ["events", "header"], "hidden": ["lanes"], "title": "Custom title"}))
        self.open()
        ids = self.page.eval_on_selector_all("#app > *", "els=>els.map(e=>(e.querySelector('.body')||{}).id||e.tagName)")
        self.assertEqual(ids[:2], ["b-events", "HEADER"])
        self.assertNotIn("b-lanes", ids)
        self.assertIn("Custom title", self.text("h1"))

    def test_hash_state_filter_collapse_and_details(self):
        self.open()
        p = self.page
        p.click("button[data-k='f-L2']")
        p.click("button[data-k='c-events']")
        p.locator("#b-lanes details summary").first.click()
        p.wait_for_function("location.hash.includes('o=L2')")
        h = p.evaluate("location.hash")
        self.assertIn("f=L2", h)
        self.assertIn("c=events", h)
        self.assertEqual(p.locator("#b-lanes tbody tr").count(), 1)
        self.assertTrue(p.is_hidden("#b-events"))
        # survives a data update with a new rev
        write_data(self.view, fresh(load("projection-sample.json"), rev=18, summary={"tasks_total": 9, "tasks_done": 4, "lanes_active": 1, "blocked": 2, "decisions_pending": 1}))
        self.wait_text("header", "4 / 9")
        self.assertEqual(p.evaluate("location.hash"), h)
        self.assertEqual(p.locator("#b-lanes tbody tr").count(), 1)
        self.assertTrue(p.is_hidden("#b-events"))
        # and a reload restores it
        p.reload()
        p.wait_for_selector("h1")
        self.assertEqual(p.locator("#b-lanes tbody tr").count(), 1)
        self.assertTrue(p.is_hidden("#b-events"))
        self.assertEqual(p.get_attribute("button[data-k='f-L2']", "aria-pressed"), "true")

    def test_keyboard_focus_visible(self):
        self.open()
        self.page.keyboard.press("Tab")  # skip link
        self.page.keyboard.press("Tab")
        outline = self.page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        self.assertNotEqual(outline, "none")


class UpdateTests(BrowserTest):
    def test_higher_rev_updates_without_reload(self):
        self.open()
        self.page.evaluate("window.__marker = 'same-document'")
        p = fresh(load("projection-sample.json"), rev=18)
        p["feature"]["title"] = "Renamed feature"
        write_data(self.view, p)
        self.wait_text("h1", "Renamed feature", timeout=UPDATE_WAIT)
        self.assertEqual(self.page.evaluate("window.__marker"), "same-document")

    def test_lower_or_equal_rev_ignored(self):
        self.open()
        for rev in (16, 17):
            p = fresh(load("projection-sample.json"), rev=rev)
            p["feature"]["title"] = "Should not appear %d" % rev
            write_data(self.view, p)
            self.page.wait_for_timeout(3600)
            self.assertNotIn("Should not appear", self.text("h1"))
        self.assertEqual(self.page.inner_text("#banners").strip(), "")

    def test_broken_data_keeps_last_good_and_banner(self):
        self.open()
        (self.view / "data.js").write_text("window.__SANDUQ_PROGRESS__ = {oops", encoding="utf-8")
        self.page.wait_for_function("document.getElementById('banners').textContent.includes('Update failed')", timeout=UPDATE_WAIT)
        self.assertIn("Add dependencies when creating a task", self.text("h1"))
        self.assertIn("T004", self.text("#b-boards"))
        # recovery clears the banner
        write_data(self.view, fresh(load("projection-sample.json"), rev=30))
        self.page.wait_for_function("!document.getElementById('banners').textContent.includes('Update failed')", timeout=UPDATE_WAIT)

    def test_a_stalled_data_load_does_not_stop_the_poller(self):
        """Under heavy load Chromium sometimes never fires onload or onerror for a file:// script; the poller must give up
        on that load and try again instead of waiting forever (this left the page stale, and made the suite flaky)."""
        self.page.add_init_script("""
            (function () {
              var dropped = false, desc = Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype, 'src');
              Object.defineProperty(HTMLScriptElement.prototype, 'src', {
                set: function (v) { if (!dropped && /data\.js/.test(v)) { dropped = true; return; } desc.set.call(this, v); },
                get: function () { return desc.get.call(this); }
              });
            })();""")
        write_data(self.view, fresh(load("projection-sample.json")))
        self.page.goto((self.view / "index.html").as_uri())
        self.page.wait_for_selector("h1", timeout=40000)
        self.assertIn("Add dependencies when creating a task", self.text("h1"))

    def test_missing_data_file_banner(self):
        self.open()
        (self.view / "data.js").unlink()
        self.page.wait_for_function("document.getElementById('banners').textContent.includes('Update failed')", timeout=UPDATE_WAIT)
        self.assertIn("T004", self.text("#b-boards"))

    def test_stale_banner_old_generated_at(self):
        proj = load("projection-sample.json")
        proj["generated_at"] = now_iso(-3600)
        self.open(proj)
        self.assertIn("Stale", self.text("#banners"))
        self.assertEqual(self.page.get_attribute("#banners", "aria-live"), "polite")

    def test_stale_banner_dirty(self):
        proj = fresh(load("projection-sample.json"))
        proj["collection"]["dirty"] = True
        self.open(proj)
        self.assertIn("pending", self.text("#banners"))

    def test_automatic_collection_unavailable(self):
        proj = fresh(load("projection-sample.json"))
        proj["collection"]["automatic"] = False
        self.open(proj)
        self.assertIn("Automatic collection unavailable", self.text("#banners"))

    def test_only_one_load_in_flight(self):
        self.open()
        n = self.page.evaluate("document.querySelectorAll('script[src^=\"data.js\"]').length")
        self.assertLessEqual(n, 1)


class OtherProjectionTests(BrowserTest):
    def test_minimal_shows_unknown(self):
        self.open(fresh(load("projection-minimal.json")))
        orch = self.text("#b-orchestrator")
        self.assertGreaterEqual(orch.count("unknown"), 5)
        self.assertEqual(self.page.locator("#b-orchestrator .fid").count(), 0)
        self.assertIn("coordinator", self.text("#b-lanes"))
        self.assertIn("unknown", self.text("#b-lanes"))
        self.assertIn("None pending", self.text("#b-decisions"))
        self.assertIn("No open blockers", self.text("#b-blockers"))
        self.assertIn("Automatic collection unavailable", self.text("#banners"))
        self.assertEqual(self.errors, [])

    def test_hostile_strings_render_as_text(self):
        self.open(fresh(load("projection-hostile.json")))
        p = self.page
        self.assertIsNone(p.evaluate("window.__PWNED__ || null"))
        self.assertEqual(p.locator("main script, main img").count(), 0)
        self.assertIn("<script>window.__PWNED__=1</script>", self.text("h1"))
        self.assertIn("مرحبا بالعالم", self.text("h1"))
        # unsafe links are not links
        self.assertEqual(p.locator("a[href^='javascript']").count(), 0)
        self.assertIn("x" * 199, self.text("#b-lanes"))
        # long ids must not blow the layout
        self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), p.evaluate("innerWidth"))
        self.assertEqual(self.errors, [])


class ResponsiveTests(BrowserTest):
    def test_360px_no_horizontal_scroll(self):
        for name in ("projection-sample.json", "projection-hostile.json", "projection-minimal.json"):
            self.open(fresh(load(name)))
            self.page.set_viewport_size({"width": 360, "height": 800})
            self.page.wait_for_timeout(150)
            sw = self.page.evaluate("document.documentElement.scrollWidth")
            self.assertLessEqual(sw, 360, name)


class DarkTests(BrowserTest):
    scheme = "dark"

    def test_dark_tokens_applied(self):
        self.open()
        bg = self.page.evaluate("getComputedStyle(document.body).backgroundColor")
        self.assertEqual(bg, "rgb(18, 25, 22)")
        self.assertEqual(self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"), "#121916")


class LightTests(BrowserTest):
    scheme = "light"

    def test_light_tokens_applied(self):
        self.open()
        self.assertEqual(self.page.evaluate("getComputedStyle(document.body).backgroundColor"), "rgb(246, 247, 244)")


class ThemeSwapTests(BrowserTest):
    def test_theme_css_swap(self):
        theme.write_assets(self.view, theme.resolve_doc({"preset": "emerald"}))
        self.open()
        self.assertEqual(self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()"), "#0f8a64")


if __name__ == "__main__":
    unittest.main()
