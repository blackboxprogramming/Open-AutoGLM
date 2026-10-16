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

The initial seven outcome test methods exercised both platform implementations (16 scenarios).
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

## Literal action envelope

The shared parser now accepts exactly one `do(...)` or `finish(...)` call with
literal keyword values. It rejects alternate callees, positional/expanded
arguments, duplicate keys, reserved `_metadata`, nonliteral expressions,
malformed strings and invalid action/message types. `Type_Name` normalizes to
`Type` regardless of keyword order. Escaped Unicode, quotes, backslashes and
newlines are decoded as Python string literals. Triple-quoted multiline strings
and whitespace between arguments are supported. `finish()` allows an omitted
message, matching the documented optional message behavior.

Compatibility change: the former Type text slicing accepted malformed quoting
and incomplete calls. These inputs now produce a failed agent step. Model output
must quote and escape text correctly. This parser does not validate every action's
inputs, permitted applications, device result or semantic completion. Coordinate
and wait validation at the handler boundary is documented below.

Parsing is limited to 65,536 response characters and 4,096 AST nodes. The parser
does not print raw payloads or include them in its own ValueError messages;
other verbose model/agent logging remains outside this change.

Parser regressions reproduced 28 failed assertions and one error against the
prior PR head `513a7f51791a2f8509ecd3d3c1249c180ace6b3f`. After the parser change,
the combined suite passes 20 test methods, including twelve cross-platform
malformed-envelope cases that never call the action executor. Compilation and
diff whitespace checks pass. Test model/device boundaries remain isolated; live
inference and device execution remain unverified.

## Coordinate and wait bounds

Android/HarmonyOS and iOS now share coordinate conversion and wait parsing in
the existing action handler module. Point gestures require exactly two integers
in the prompt-documented 0-999 range, and positive integer screenshot dimensions.
Both swipe endpoints are validated before any device control. Boolean, float,
negative, oversized and malformed coordinates fail; invalid sensitive taps do
not invoke confirmation callbacks. Valid cancellation behavior remains intact.

Pixel scaling uses integer floor arithmetic, including small one-pixel screens.
This preserves the intended scaling and avoids floating-point rounding losing a
pixel (e.g. x=290 on a 100-pixel-wide image maps to x=29).

Wait retains its one-second default, numeric strings and the documented
`"x seconds"` syntax. A wait must be finite and within 0-30 seconds. Invalid
duration text now fails rather than silently sleeping for one second; numeric
non-string values, NaN, infinity, negative and excessive waits also fail before
sleep. Longer pauses require a separately designed wait/cancellation policy.

The initial eight bound-test methods reproduced 82 failed assertions against
`c2fe48a23986f446bc9ae6efc5c0ebcad8a71407`. With the fixes and an additional valid
swipe test, all 29 combined test methods pass. The new tests use the actual
Android and iOS handlers, replacing device and clock boundaries only. Valid taps
and swipes reach those boundaries with expected pixel arguments; invalid
gestures never reach device controls, and invalid waits never reach sleep.
Compilation and whitespace checks pass. This is offline verification; real
device outcomes and inference remain unverified.
