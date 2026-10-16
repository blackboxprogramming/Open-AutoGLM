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

## Keyboard cleanup on text-entry failures

Once keyboard selection returns the original IME, the Android/HarmonyOS handler
attempts to restore that exact IME on the same selected device after clearing,
typing, delay errors and interruptions. Invalid non-string text fails before
keyboard selection or clearing. A restoration error after otherwise successful
typing fails the action; combined input/restoration errors retain both messages.
Active interruptions propagate even when cleanup also fails.

ADB and HarmonyOS restoration commands now use checked subprocess execution;
HarmonyOS no longer swallows restoration transport errors. The existing
HarmonyOS no-op for an absent original IME remains. Successful command exit does
not independently prove the device applied the keyboard change.

Nine handler cleanup tests reproduced 13 failed assertions against
`3df8034c6a409442a68e44ead389512e48851ac2`; four restore-adapter tests reproduced
three additional failed assertions against the original adapters. All 42
combined test methods now pass, with compilation and whitespace checks passing.
The restore-adapter tests load actual source, including the HDC command helper,
and replace subprocess execution only. No keyboard or device was changed here.

This cleanup slice initially covered selection calls that returned an original
IME. The checked-input-command section below extends coverage to selection
rollback and text-command exit handling. Tests establish restoration attempts
and error propagation, not live keyboard restoration or successful on-device
text entry. iOS keyboard lifecycle remains separate work.

## Checked text-input commands and selection rollback

All ADB/HDC commands in the two existing input adapter modules now use checked
subprocess execution. Nonzero clear/type/query/switch/restore exits propagate
as RuntimeError diagnostics containing the transport and exit status, without
copying the command's typed text or base64 payload. This changes nonzero restore
errors from CalledProcessError to RuntimeError; public functions retain their
existing success return types. Existing transport errors continue to propagate.
Other verbose logging, including opt-in HDC command logging, is unchanged.

HarmonyOS stops remaining multiline input if a text or ENTER command fails,
rather than printing an error and continuing. Its keyboard query returns only
stdout and no longer converts command failures into an empty successful result.
The successful empty-IME placeholder behavior remains; actual HarmonyOS keyboard
selection support is not added.

Android queries read only stdout and require one nonempty package/component IME
without whitespace. Unknown or malformed original IDs fail before switching or
clearing text. Switching/warmup failures attempt restoration once the original
IME is known. Combined selection/restoration errors preserve both status
diagnostics; an interruption still propagates after the rollback attempt.
An already selected ADB keyboard skips the redundant switch.

The first eight command tests reproduced nine failed assertions and three errors
against `90dc3f8e3881e1967b15fa3e8bb6fb3f169c3235`. With additional rollback and
handler/adapter collaboration coverage, all 54 test methods pass. Actual input
adapter functions and the HDC helper run with subprocess outcomes isolated;
the collaboration tests confirm command failures reach the real handler as
failed actions followed by restoration attempts. Compilation and whitespace
checks pass. No live inference or device commands were run, and a zero process
exit still does not independently verify the resulting on-device state.
