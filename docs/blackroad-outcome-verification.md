# Failed steps retain failed outcomes

When a model response cannot be parsed, both Android/HarmonyOS and iOS agents
now return a terminal `StepResult(success=False)` without executing an action.
When execution raises, the agent returns a failed result with the original action
and does not execute a synthetic successful `finish`. Failed terminal actions no
longer print the completion banner. `run()` retains its string return type and
uses `Task failed` when a failed terminal result has no message.

This supports truthful status when a future RoadOS Computer integration reports
agent progress alongside RoadTrip. It does not add that integration or prove a
model's explicit `finish` claim matches the device's actual state.

## Verification

Baseline: `86f55382982fb054e8fc98ca80609dff8a2cdc3c`.

```sh
python -m unittest discover -s tests -v
python -m compileall -q phone_agent tests
```

The seven test methods exercise both platform implementations (16 scenarios).
Before the production change, ten subtests failed: parse failure, execution
exception, failed completion banner and both `run()` return sites. After the
change, all seven methods passed; compilation also passed.

Tests load the actual agent/parser source with isolated replacements for optional
model SDK and device boundaries. They require only Python's standard library and
do not connect a device, run inference, install dependencies or establish live
Android, HarmonyOS or iOS control. Live deployment remains unverified. No GitHub
Actions workflow is added.

Existing Apache-2.0 terms and upstream attribution remain authoritative for this
source. Model weights, assets and dependencies require their own review before
distribution or integration.
