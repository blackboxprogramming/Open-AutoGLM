"""Exercise real restore adapters and HDC helper at the subprocess boundary."""

import subprocess
import types
import unittest
from unittest.mock import Mock

from test_step_outcomes import load_source, module


def adapters(returncode=0, error=None):
    def run(command, **kwargs):
        if error:
            raise error
        result = subprocess.CompletedProcess(command, returncode, stdout="", stderr="")
        if kwargs.get("check"):
            result.check_returncode()
        return result

    adb_run, hdc_run = Mock(side_effect=run), Mock(side_effect=run)
    adb = load_source("restore_adb", "phone_agent/adb/input.py", {})
    adb.subprocess = types.SimpleNamespace(run=adb_run)
    connection = load_source("restore_hdc_connection", "phone_agent/hdc/connection.py", {
        "phone_agent.config.timing": module("timing", TIMING_CONFIG=None),
    })
    connection.subprocess = types.SimpleNamespace(run=hdc_run)
    hdc = load_source("restore_hdc", "phone_agent/hdc/input.py", {
        "phone_agent.hdc.connection": connection,
    })
    return [(adb, adb_run, "-s"), (hdc, hdc_run, "-t")]


class KeyboardRestoreAdapterTests(unittest.TestCase):
    def test_successful_restore_keeps_selected_device_and_original_ime(self):
        for device in (None, "selected-device"):
            for adapter, runner, selector in adapters():
                with self.subTest(adapter=adapter.__name__, device=device):
                    adapter.restore_keyboard("original-ime", device)
                    command = runner.call_args.args[0]
                    prefix = ["adb"] if selector == "-s" else ["hdc"]
                    if device:
                        prefix += [selector, device]
                    self.assertEqual(command, prefix + ["shell", "ime", "set", "original-ime"])
                    self.assertEqual(runner.call_count, 1)

    def test_nonzero_restore_exit_is_reported(self):
        for adapter, _, _ in adapters(returncode=7):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(RuntimeError) as caught:
                adapter.restore_keyboard("original-ime", "selected-device")
            self.assertIn("7", str(caught.exception))

    def test_restore_transport_error_is_not_swallowed(self):
        for adapter, _, _ in adapters(error=OSError("transport unavailable")):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(OSError):
                adapter.restore_keyboard("original-ime", "selected-device")

    def test_harmony_missing_original_ime_retains_noop_behavior(self):
        hdc, runner, _ = adapters()[1]
        hdc.restore_keyboard("", "selected-device")
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
