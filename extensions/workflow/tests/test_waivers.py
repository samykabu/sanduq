import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import waivers


class WaiverTests(unittest.TestCase):
    def setUp(self):
        self.pr = {'number': 7, 'user': {'login': 'author'}, 'head': {'sha': 'a' * 40}}
        self.policy = {'decisions': {'authorized_users': ['maintainer']}}

    def comment(self, login='maintainer', expiry='2026-10-01', head=None, association='NONE'):
        item = {'version': 1, 'pr': 7, 'feature': 'specs/7-bug', 'rule': 'tasks',
                'head_sha': head or 'a' * 40, 'expires': expiry, 'reason': 'Known split task'}
        return {'user': {'login': login, 'type': 'User'}, 'author_association': association,
                'body': '<!-- sanduq-gate-waiver ' + json.dumps(item) + ' -->\nReason: Known split task',
                'html_url': 'https://github.com/acme/app/issues/7#issuecomment-9'}

    def run_verify(self, comment):
        class GitHub:
            def api(_, endpoint, pages=False):
                if '/pulls/' in endpoint:
                    return self.pr
                return [comment]
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(waivers, 'github_repository', return_value='acme/app'):
            return waivers.verify(Path(folder), 7, 'specs/7-bug', 'tasks', self.policy,
                                  GitHub(), today=date(2026, 9, 24))

    def test_authorized_exact_waiver(self):
        result = self.run_verify(self.comment())
        self.assertEqual((result['rule'], result['reviewer']), ('tasks', 'maintainer'))

    def test_author_only_expired_or_old_head_cannot_waive(self):
        for comment in (self.comment(login='author'), self.comment(expiry='2026-09-23'),
                        self.comment(head='b' * 40)):
            with self.subTest(comment=comment['body'], login=comment['user']['login']):
                with self.assertRaisesRegex(waivers.WorkflowError, 'WAIVER_NOT_VERIFIED'):
                    self.run_verify(comment)

    def test_rules_map_to_exact_error(self):
        self.assertEqual(waivers.error_rule('INCOMPLETE_TASKS'), 'tasks')
        self.assertIsNone(waivers.error_rule('CHECKPOINT_MISSING_OR_WRONG_FEATURE'))


if __name__ == '__main__':
    unittest.main()
