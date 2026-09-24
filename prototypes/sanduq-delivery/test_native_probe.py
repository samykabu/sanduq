"""Run with: uv run --project <spec-kit checkout> python -m unittest <this file>."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from specify_cli.workflows.base import StepContext, StepStatus
from specify_cli.workflows.engine import WorkflowEngine
from specify_cli.workflows.steps.command import CommandStep


PROTOTYPE = Path(__file__).with_name('workflow.yml')


class NativeProbe(unittest.TestCase):
    def test_definition_validates(self):
        engine = WorkflowEngine(PROTOTYPE.parent)
        self.assertEqual(engine.validate(engine.load_workflow(PROTOTYPE)), [])

    def test_claude_and_codex_dispatch_argv_without_real_agent_call(self):
        with tempfile.TemporaryDirectory() as folder:
            for integration in ('claude', 'codex'):
                with self.subTest(integration=integration):
                    with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
                        result = CommandStep().execute(
                            {'id': 'specify', 'command': 'speckit.specify',
                             'integration': integration, 'input': {'args': '42'}},
                            StepContext(project_root=folder, default_integration=integration))
                    self.assertEqual(result.status, StepStatus.COMPLETED)
                    argv = run.call_args.args[0]
                    self.assertIn('speckit-specify', ' '.join(argv))
                    self.assertEqual(argv[1], 'exec' if integration == 'codex' else '-p')

    def test_command_success_does_not_require_receipt(self):
        # The native engine marks a successful integration process completed
        # even when Sanduq's required checkpoint/receipt has not been written.
        with patch.object(CommandStep, '_try_dispatch', return_value={
                'exit_code': 0, 'stdout': '', 'stderr': ''}):
            result = CommandStep().execute(
                {'id': 'tasks', 'command': 'speckit.tasks', 'integration': 'codex',
                 'input': {'args': '42'}}, StepContext(default_integration='codex'))
        self.assertEqual(result.status, StepStatus.COMPLETED)


if __name__ == '__main__':
    unittest.main()
