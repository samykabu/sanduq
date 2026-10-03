import unittest
from pathlib import Path

import yaml
from packaging.specifiers import SpecifierSet

REPO = Path(__file__).resolve().parents[3]
# Presets that package.py bundles into the workflow package.
BUNDLED_PRESETS = ('workflow', 'scope-gate', 'scope-brainstorm')


def speckit_range(manifest):
    return yaml.safe_load(manifest.read_text(encoding='utf-8'))['requires']['speckit_version']


class SpeckitCompatibilityTests(unittest.TestCase):
    """A bundled preset whose spec-kit range is narrower than the extension's fails
    `install.py --apply` with INSTALL_ROLLED_BACK on a spec-kit the extension accepts."""

    def test_bundled_presets_accept_every_speckit_the_extension_accepts(self):
        extension = SpecifierSet(speckit_range(REPO / 'extensions/workflow/extension.yml'))
        for name in BUNDLED_PRESETS:
            with self.subTest(preset=name):
                preset = SpecifierSet(speckit_range(REPO / 'presets' / name / 'preset.yml'))
                for version in ('1.0.0', '1.0.11', '1.1.0', '1.1.1', '1.1.1.dev0', '1.9.0'):
                    if extension.contains(version, prereleases=True):
                        self.assertTrue(preset.contains(version, prereleases=True),
                                        f'{name} rejects spec-kit {version}')


if __name__ == '__main__':
    unittest.main()
