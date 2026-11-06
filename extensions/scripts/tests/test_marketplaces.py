"""E7: the Codex marketplace lists the same bundles at the same pins as the Claude one."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


class MarketplaceTests(unittest.TestCase):
    def test_codex_marketplace_mirrors_claude(self):
        claude, codex = load('.claude-plugin/marketplace.json'), load('.agents/plugins/marketplace.json')
        self.assertEqual(codex['name'], claude['name'])
        pins = lambda doc: {p['name']: p['source'] for p in doc['plugins']}
        self.assertEqual(pins(codex), pins(claude))
        categories = {p['name']: p['category'] for p in claude['plugins']}
        for plugin in codex['plugins']:
            self.assertEqual(plugin['source']['source'], 'git-subdir')
            self.assertEqual(plugin['category'], categories[plugin['name']])
            self.assertEqual(plugin['policy'], {'installation': 'AVAILABLE'})


if __name__ == '__main__':
    unittest.main()
