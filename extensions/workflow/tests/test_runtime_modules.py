"""W9: `workflow.py` re-exports every name of the runtime modules, and the operation memo has one home."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import workflow as w  # noqa: E402
import wf_core  # noqa: E402
import wf_health  # noqa: E402
from runtime_patch import MODULES, patch_runtime  # noqa: E402


class RuntimeModuleTests(unittest.TestCase):
    def test_every_module_name_is_reexported_except_the_memo(self):
        for name in MODULES[1:]:
            module = sys.modules[name]
            for node in ast.parse((SCRIPTS / (name + '.py')).read_text(encoding='utf-8')).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    keys = [node.name]
                elif isinstance(node, ast.Assign):
                    keys = [t.id for t in ast.walk(node.targets[0]) if isinstance(t, ast.Name)]
                else:
                    continue
                for key in keys:
                    if key != '_OPERATION':
                        with self.subTest(module=name, name=key):
                            self.assertIs(getattr(w, key), getattr(module, key))
        self.assertNotIn('_OPERATION', vars(w))

    def test_the_operation_memo_lives_in_wf_core(self):
        self.assertIsNone(wf_core._OPERATION)
        with w.operation():
            self.assertEqual(wf_core._OPERATION, {})
        self.assertIsNone(wf_core._OPERATION)

    def test_memory_handoff_names_are_workflow_globals(self):
        """memory_handoff reads the runtime through `SimpleNamespace(**globals())` of workflow.py."""
        tree = ast.parse((SCRIPTS / 'memory_handoff.py').read_text(encoding='utf-8'))
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == 'w'}
        self.assertTrue(used)
        self.assertEqual(sorted(used - set(vars(w))), [])

    def test_scope_path_loading_reaches_checkpoint_identity(self):
        path = SCRIPTS / 'scope/workflow_policy.py'
        spec = importlib.util.spec_from_file_location('w9_workflow_policy', path)
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        runtime = policy._workflow_module()
        self.assertIsNotNone(runtime)
        self.assertIs(runtime.verify_checkpoint_identity, sys.modules['wf_identity'].verify_checkpoint_identity)

    def test_patch_runtime_reaches_callers_in_every_module(self):
        with patch_runtime('doctor', return_value={'ok': True, 'errors': []}) as doctor:
            self.assertIs(w.doctor, doctor)
            self.assertIs(wf_health.doctor, doctor)  # cached_doctor's lookup
        self.assertIsNot(wf_health.doctor, doctor)
        self.assertIs(wf_health.doctor, w.doctor)


if __name__ == '__main__':
    unittest.main()
