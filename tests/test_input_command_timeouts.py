"""Verify finite command waits and cleanup through real adapter/handler code."""

import subprocess
import sys
import unittest
from unittest.mock import patch

from test_keyboard_restore_adapters import adapters
import test_keyboard_cleanup
from test_step_outcomes import load_source, module


class InputCommandTimeoutTests(unittest.TestCase):
    def test_every_input_operation_has_a_ten_second_timeout(self):
        for operation in ("type_text", "clear_text", "restore_keyboard", "detect_and_set_adb_keyboard"):
            for adapter, runner, _ in adapters():
                with self.subTest(adapter=adapter.__name__, operation=operation):
                    runner.side_effect = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
                    if operation == "type_text":
                        adapter.type_text("hello\nworld", "device")
                    elif operation == "restore_keyboard":
                        adapter.restore_keyboard("original/.Ime", "device")
                    else:
                        getattr(adapter, operation)("device")
                    self.assertGreater(runner.call_count, 0)
                    for invocation in runner.call_args_list:
                        self.assertEqual(invocation.kwargs.get("timeout"), 10.0)

    def test_timeout_errors_do_not_expose_command_or_output_payloads(self):
        error = subprocess.TimeoutExpired(["private-command-1729"], 10.0,
                                          output=b"private-output", stderr=b"private-error")
        for adapter, runner, _ in adapters(error=error):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(RuntimeError) as caught:
                adapter.type_text("private-text", "device")
            message = str(caught.exception)
            self.assertIn("timed out", message)
            self.assertIn("10", message)
            self.assertNotIn("private", message)
            self.assertEqual(runner.call_count, 1)

    def test_initial_keyboard_query_timeout_stops_without_guessing_restore(self):
        for adapter, runner, _ in adapters(error=subprocess.TimeoutExpired(["query"], 10.0)):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(RuntimeError):
                adapter.detect_and_set_adb_keyboard("device")
            self.assertEqual(runner.call_count, 1)

    def test_input_timeout_reaches_handler_and_attempts_restore(self):
        for failure in ("clear", "type"):
            for adapter, runner, _ in adapters():
                with self.subTest(adapter=adapter.__name__, failure=failure):
                    def run(command, **kwargs):
                        is_clear = "ADB_CLEAR_TEXT" in command or command[-1] == "2017"
                        is_type = command[-1] in {"aGVsbG8=", "hello"}
                        if (failure == "clear" and is_clear) or (failure == "type" and is_type):
                            raise subprocess.TimeoutExpired(command, 10.0)
                        return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
                    runner.side_effect = run
                    _, _, device, handler = test_keyboard_cleanup.KeyboardCleanupTests().make_handler()
                    for name in ("detect_and_set_adb_keyboard", "clear_text", "type_text", "restore_keyboard"):
                        setattr(device, name, getattr(adapter, name))
                    result = handler.execute({"_metadata": "do", "action": "Type", "text": "hello"}, 1080, 1920)
                    self.assertFalse(result.success)
                    self.assertIn("timed out", result.message)
                    self.assertNotIn("hello", result.message)
                    self.assertNotIn("aGVsbG8=", result.message)
                    self.assertEqual(runner.call_args.args[0][-4:], ["shell", "ime", "set", "original/.Ime"])

    def test_android_switch_and_restore_timeouts_keep_failed_result(self):
        adapter, runner, _ = adapters()[0]
        def run(command, **kwargs):
            if "set" in command:
                raise subprocess.TimeoutExpired(command, 10.0)
            return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
        runner.side_effect = run
        with self.assertRaises(RuntimeError) as caught:
            adapter.detect_and_set_adb_keyboard("device")
        self.assertIn("Keyboard selection failed", str(caught.exception))
        self.assertIn("restoration failed", str(caught.exception))
        self.assertNotIn("original/.Ime", str(caught.exception))
        self.assertEqual(runner.call_count, 3)

    def test_real_local_child_is_terminated_and_reaped_on_timeout(self):
        adb = load_source("timeout_real_adb", "phone_agent/adb/input.py", {})
        connection = load_source("timeout_real_hdc_connection", "phone_agent/hdc/connection.py", {
            "phone_agent.config.timing": module("timing", TIMING_CONFIG=None),
        })
        connection._HDC_VERBOSE = False
        hdc = load_source("timeout_real_hdc", "phone_agent/hdc/input.py", {
            "phone_agent.hdc.connection": connection,
        })
        real_popen = subprocess.Popen
        for adapter in (adb, hdc):
            with self.subTest(adapter=adapter.__name__):
                adapter.INPUT_COMMAND_TIMEOUT_SECONDS = 0.1
                children = []
                def spawn(*args, **kwargs):
                    child = real_popen(*args, **kwargs)
                    children.append(child)
                    return child
                with patch("subprocess.Popen", side_effect=spawn):
                    with self.assertRaises(RuntimeError) as caught:
                        adapter._run_input_command([
                            sys.executable, "-c", "import time; time.sleep(5)",
                        ])
                self.assertIn("timed out", str(caught.exception))
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())


if __name__ == "__main__":
    unittest.main()
