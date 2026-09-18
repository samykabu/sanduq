import json
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
import test_workflow as fixture


class SchemaContractTests(unittest.TestCase):
    setUp = fixture.WorkflowTests.setUp
    configure = fixture.WorkflowTests.configure
    usage = fixture.WorkflowTests.usage
    receipt = fixture.WorkflowTests.receipt
    run_object = fixture.WorkflowTests.run_object

    def test_runtime_checkpoints_and_receipts_match_published_schemas(self):
        directory = Path(__file__).resolve().parents[1] / 'schemas'
        schemas = {path.name: json.loads(path.read_text(encoding='utf-8')) for path in directory.glob('*.schema.json')}
        registry = Registry()
        for name, schema in schemas.items():
            Draft202012Validator.check_schema(schema)
            registry = registry.with_resource('https://sanduq.local/schemas/' + name, Resource.from_contents(schema))
        validator = Draft202012Validator(schemas['checkpoint-v1.schema.json'], registry=registry, format_checker=FormatChecker())
        run = self.run_object()
        validator.validate(run.load())
        for stage in fixture.w.stages(self.policy):
            claim = run.claim(self.usage(), finalize=stage == 'pr')
            validator.validate(run.load())
            run.complete(claim['token'], self.receipt(stage))
            validator.validate(run.load())
