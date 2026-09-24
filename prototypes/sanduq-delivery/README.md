# Sanduq Delivery native workflow experiment

This directory is deliberately outside the released workflow extension. It
tests Spec Kit native sequencing without changing Sanduq's production
dispatcher. The native command step accepts an integration process exit code
without checking a Sanduq receipt; static receipt guards follow each command
in this experiment. It is **not approved for production scheduling**.

In a disposable project with the Sanduq workflow extension installed:

```text
specify workflow add --dev /path/to/sanduq/prototypes/sanduq-delivery
specify workflow info sanduq-delivery
```

The guard's static shell command expects this `prototypes/sanduq-delivery/`
folder in the project checkout, so installing only `workflow.yml` is not an
executable end-to-end package. It is intentionally separate from Sanduq's
consumer installer. Run `test_native_probe.py` with the pinned Spec Kit
checkout; see [the result](../../docs/native-workflow-prototype-results.md).
