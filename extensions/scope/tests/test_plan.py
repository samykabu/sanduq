import copy
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'scripts/accept_plan.py'
spec = importlib.util.spec_from_file_location('accept_plan', path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.graph = {'issues': [{'number': 1, 'dependencies': [], 'children': []},
                                 {'number': 2, 'dependencies': [1], 'children': []},
                                 {'number': 3, 'dependencies': [], 'children': [1, 2]}]}
        self.diagram = {'nodes': [{'id': 'first'}, {'id': 'second'}], 'edges': [{'from': 'first', 'to': 'second'}]}
        self.mapping = {'graph_sha256': 'abc', 'issue_to_node': {'1': 'first', '2': 'second'}}

    def test_complete_mapping(self):
        m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_stale_graph_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stale'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'changed')

    def test_missing_issue_rejected(self):
        del self.mapping['issue_to_node']['2']
        with self.assertRaisesRegex(ValueError, 'every executable'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_missing_dependency_path_rejected(self):
        self.diagram['edges'] = []
        with self.assertRaisesRegex(ValueError, 'omits dependency'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependent_same_wave_rejected(self):
        self.mapping['issue_to_node']['2'] = 'first'
        with self.assertRaisesRegex(ValueError, 'parallel implementation wave'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependency_on_parent_rejected(self):
        self.graph['issues'][1]['dependencies'] = [3]
        with self.assertRaisesRegex(ValueError, 'aggregate'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')

    def test_dependency_cycle_rejected(self):
        self.graph['issues'][0]['dependencies'] = [2]
        self.diagram['edges'].append({'from': 'second', 'to': 'first'})
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            m.check_graph_mapping(self.graph, self.diagram, self.mapping, 'abc')


if __name__ == '__main__':
    unittest.main()
