"""Perceptual review cannot accept stale or missing diagram evidence."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from accept_plan import validate_review


class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.html = self.root / 'plan.html'
        self.html.write_text('<html>Current diagram</html>', encoding='utf-8')
        self.screenshot = self.root / 'review.png'
        self.screenshot.write_bytes(b'fixture screenshot bytes')
        self.review = {
            'html_sha256': hashlib.sha256(self.html.read_bytes()).hexdigest(),
            'passed': True, 'reviewer': 'image-capable reviewer', 'findings': [],
            'screenshots': [{'path': 'review.png', 'sha256': hashlib.sha256(self.screenshot.read_bytes()).hexdigest()}],
        }

    def test_current_review_is_accepted(self):
        validate_review(self.root, self.html, self.review)

    def test_changed_html_is_rejected(self):
        self.html.write_text('New diagram', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'current HTML'):
            validate_review(self.root, self.html, self.review)

    def test_changed_or_deleted_screenshot_is_rejected(self):
        self.screenshot.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'missing, changed'):
            validate_review(self.root, self.html, self.review)
        self.screenshot.unlink()
        with self.assertRaisesRegex(ValueError, 'missing, changed'):
            validate_review(self.root, self.html, self.review)

    def test_unresolved_findings_or_no_images_are_rejected(self):
        self.review['findings'] = ['Unreadable label']
        with self.assertRaisesRegex(ValueError, 'zero unresolved'):
            validate_review(self.root, self.html, self.review)
        self.review['findings'] = []
        self.review['screenshots'] = []
        with self.assertRaisesRegex(ValueError, 'actual screenshot'):
            validate_review(self.root, self.html, self.review)

    def test_outside_project_image_is_rejected(self):
        self.review['screenshots'][0]['path'] = '../review.png'
        with self.assertRaisesRegex(ValueError, 'outside the project'):
            validate_review(self.root, self.html, self.review)
