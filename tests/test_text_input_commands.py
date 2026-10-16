"""Actual input adapters with deterministic subprocess outcomes."""

import subprocess
import unittest

from test_keyboard_restore_adapters import adapters
import test_keyboard_cleanup


class TextInputCommandTests(unittest.TestCase):
    def test_failed_type_and_clear_commands_stop_and_hide_payload(self):
        secret = "private-payload-1729"
        for operation in ("type_text", "clear_text"):
            for adapter, runner, _ in adapters(returncode=7):
                with self.subTest(adapter=adapter.__name__, operation=operation):
                    with self.assertRaises(RuntimeError) as caught:
                        if operation == "type_text":
                            adapter.type_text(secret, "device")
                        else:
                            adapter.clear_text("device")
                    self.assertIn("7", str(caught.exception))
                    self.assertNotIn(secret, str(caught.exception))
                    self.assertNotIn("Command [", str(caught.exception))
                    self.assertEqual(runner.call_count, 1)

    def test_harmony_enter_failure_stops_remaining_lines(self):
        adapter, runner, _ = adapters()[1]
        runner.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CalledProcessError(9, ["hdc", "private-payload"]),
        ]
        with self.assertRaises(RuntimeError) as caught:
            adapter.type_text("one\ntwo", "device")
        self.assertIn("9", str(caught.exception))
        self.assertNotIn("private-payload", str(caught.exception))
        self.assertEqual(runner.call_count, 2)

    def test_harmony_success_preserves_blank_lines_and_selected_device(self):
        adapter, runner, _ = adapters()[1]
        adapter.type_text("one\n\nthree", "device")
        self.assertEqual([item.args[0] for item in runner.call_args_list], [
            ["hdc", "-t", "device", "shell", "uitest", "uiInput", "text", "one"],
            ["hdc", "-t", "device", "shell", "uitest", "uiInput", "keyEvent", "2054"],
            ["hdc", "-t", "device", "shell", "uitest", "uiInput", "keyEvent", "2054"],
            ["hdc", "-t", "device", "shell", "uitest", "uiInput", "text", "three"],
        ])

    def test_failed_keyboard_read_never_attempts_switch_or_warmup(self):
        for adapter, runner, _ in adapters(returncode=7):
            with self.subTest(adapter=adapter.__name__), self.assertRaises(RuntimeError):
                adapter.detect_and_set_adb_keyboard("device")
            self.assertEqual(runner.call_count, 1)

    def test_android_uses_stdout_only_and_restores_after_warmup_failure(self):
        adapter, runner, _ = adapters()[0]
        def run(command, **kwargs):
            if "ADB_INPUT_B64" in command:
                raise subprocess.CalledProcessError(8, command)
            return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="warning ignored\n")
        runner.side_effect = run
        with self.assertRaises(RuntimeError):
            adapter.detect_and_set_adb_keyboard("device")
        self.assertEqual(runner.call_args.args[0], ["adb", "-s", "device", "shell", "ime", "set", "original/.Ime"])
        self.assertEqual(runner.call_count, 4)

    def test_android_switch_failure_attempts_original_keyboard_restore(self):
        adapter, runner, _ = adapters()[0]
        def run(command, **kwargs):
            if command[-1] == "com.android.adbkeyboard/.AdbIME":
                raise subprocess.CalledProcessError(6, command)
            return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
        runner.side_effect = run
        with self.assertRaises(RuntimeError):
            adapter.detect_and_set_adb_keyboard("device")
        self.assertEqual(runner.call_count, 3)
        self.assertEqual(runner.call_args.args[0][-1], "original/.Ime")

    def test_android_unknown_original_ime_stops_before_selection(self):
        for value in ("", "null", "/", "original/", "/.Ime", "warning without component", "two/.Ime\nother/.Ime"):
            adapter, runner, _ = adapters()[0]
            runner.return_value = subprocess.CompletedProcess([], 0, stdout=value, stderr="")
            runner.side_effect = None
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapter.detect_and_set_adb_keyboard("device")
            self.assertEqual(runner.call_count, 1)

    def test_android_success_returns_exact_original_ime(self):
        adapter, runner, _ = adapters()[0]
        runner.side_effect = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="warning ignored")
        self.assertEqual(adapter.detect_and_set_adb_keyboard("device"), "original/.Ime")
        self.assertEqual(runner.call_count, 3)

    def test_android_existing_adb_keyboard_skips_redundant_switch(self):
        adapter, runner, _ = adapters()[0]
        runner.side_effect = lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="com.android.adbkeyboard/.AdbIME\n", stderr="")
        self.assertEqual(adapter.detect_and_set_adb_keyboard("device"), "com.android.adbkeyboard/.AdbIME")
        self.assertEqual(runner.call_count, 2)
        self.assertIn("ADB_INPUT_B64", runner.call_args.args[0])

    def test_android_selection_and_rollback_failures_retain_both_statuses(self):
        adapter, runner, _ = adapters()[0]
        def run(command, **kwargs):
            if "ADB_INPUT_B64" in command:
                raise subprocess.CalledProcessError(8, command)
            if command[-1] == "original/.Ime":
                raise subprocess.CalledProcessError(9, command)
            return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
        runner.side_effect = run
        with self.assertRaises(RuntimeError) as caught:
            adapter.detect_and_set_adb_keyboard("device")
        self.assertIn("8", str(caught.exception))
        self.assertIn("9", str(caught.exception))
        self.assertEqual(runner.call_count, 4)

    def test_android_warmup_interruption_propagates_after_rollback_attempt(self):
        adapter, runner, _ = adapters()[0]
        def run(command, **kwargs):
            if "ADB_INPUT_B64" in command:
                raise KeyboardInterrupt()
            if command[-1] == "original/.Ime":
                raise subprocess.CalledProcessError(9, command)
            return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
        runner.side_effect = run
        with self.assertRaises(KeyboardInterrupt):
            adapter.detect_and_set_adb_keyboard("device")
        self.assertEqual(runner.call_args.args[0][-1], "original/.Ime")

    def test_real_adapters_propagate_text_failures_through_handler_and_cleanup(self):
        for failure in ("clear", "type"):
            for adapter, runner, selector in adapters():
                with self.subTest(adapter=adapter.__name__, failure=failure):
                    def run(command, **kwargs):
                        is_clear = "ADB_CLEAR_TEXT" in command or command[-1] == "2017"
                        is_type = command[-1] in {"aGVsbG8=", "hello"}
                        if (failure == "clear" and is_clear) or (failure == "type" and is_type):
                            raise subprocess.CalledProcessError(7, command)
                        return subprocess.CompletedProcess(command, 0, stdout="original/.Ime\n", stderr="")
                    runner.side_effect = run
                    _, _, device, handler = test_keyboard_cleanup.KeyboardCleanupTests().make_handler()
                    for name in ("detect_and_set_adb_keyboard", "clear_text", "type_text", "restore_keyboard"):
                        setattr(device, name, getattr(adapter, name))
                    result = handler.execute({"_metadata": "do", "action": "Type", "text": "hello"}, 1080, 1920)
                    self.assertFalse(result.success)
                    self.assertIn("7", result.message)
                    self.assertNotIn("hello", result.message)
                    self.assertEqual(runner.call_args.args[0][-4:], ["shell", "ime", "set", "original/.Ime"])


if __name__ == "__main__":
    unittest.main()
