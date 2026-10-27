"""AHMED-03: a misspelt workflow.yml key is refused with POLICY_KEY_UNKNOWN, its path and the closest known key."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w  # noqa: E402


def typos(key):
    """One-letter typos: the last letter doubled and, for longer keys, the second letter dropped."""
    found = [key + key[-1]]
    if len(key) > 3:
        found.append(key[0] + key[2:])
    return found


def with_key(policy, section, key):
    """`policy` with `key` set under the dotted `section` (None: the top level), creating the section."""
    target = policy
    for part in (section.split('.') if section else ()):
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[key] = {}
    return policy


class PolicyKeyTypoTests(unittest.TestCase):
    def test_every_documented_key_with_a_one_letter_typo_is_refused_with_a_suggestion(self):
        base = w.default_policy(False, False)
        for section, allowed in w.POLICY_KEYS.items():
            for key in allowed:
                for typo in typos(key):
                    path = (section + '.' if section else '')
                    with self.subTest(path=path + typo), self.assertRaises(w.WorkflowError) as caught:
                        w.validate_policy(with_key(copy.deepcopy(base), section, typo))
                    message = str(caught.exception)
                    self.assertTrue(message.startswith('POLICY_KEY_UNKNOWN: ' + path + typo + '; did you mean ' +
                                                       path + key + '?'), message)
                    self.assertIn('Allowed keys', message)
                    self.assertIn('newer Workflow release', message)
                    self.assertIn('upgrade.py --version', message)

    def test_readme_snippet_keys_validate_and_unknown_keys_without_a_match_say_so(self):
        policy = w.default_policy(False, False)
        policy['profiles'] = {'enabled': True}
        policy['clarification'].update(in_session_first_round=True, max_questions_per_round=6)
        policy['scope'] = {'board_cache_seconds': 300}
        w.validate_policy(policy)
        policy['zzz'] = 1
        with self.assertRaisesRegex(w.WorkflowError, r'POLICY_KEY_UNKNOWN: zzz; no similar key exists\.'):
            w.validate_policy(policy)


if __name__ == '__main__':
    unittest.main()
