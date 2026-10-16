"""Verify the real text-entry handler restores state across failure paths."""

import types
import unittest
from unittest.mock import Mock, call

from test_action_bounds import load_handlers


class KeyboardCleanupTests(unittest.TestCase):
    def make_handler(self):
        android, _, factory, _ = load_handlers()
        android.TIMING_CONFIG = types.SimpleNamespace(action=types.SimpleNamespace(
            keyboard_switch_delay=0, text_clear_delay=0,
            text_input_delay=0, keyboard_restore_delay=0,
        ))
        device = factory.return_value
        device.detect_and_set_adb_keyboard.return_value = "original-ime"
        handler = android.ActionHandler(device_id="selected-device")
        return android, factory, device, handler

    def execute(self, handler, text="hello"):
        return handler.execute({"_metadata": "do", "action": "Type", "text": text}, 1080, 1920)

    def test_success_preserves_order_device_and_original_keyboard(self):
        for text in ("", 'Alexa’s road\nsecond line'):
            with self.subTest(text=text):
                android, _, device, handler = self.make_handler()
                events = Mock()
                events.attach_mock(device, "device")
                events.attach_mock(android.time.sleep, "sleep")
                self.assertTrue(self.execute(handler, text).success)
                self.assertEqual(events.mock_calls, [
                    call.device.detect_and_set_adb_keyboard("selected-device"),
                    call.sleep(0), call.device.clear_text("selected-device"),
                    call.sleep(0), call.device.type_text(text, "selected-device"),
                    call.sleep(0), call.device.restore_keyboard("original-ime", "selected-device"),
                    call.sleep(0),
                ])

    def test_clear_failure_restores_without_typing(self):
        _, _, device, handler = self.make_handler()
        device.clear_text.side_effect = RuntimeError("clear failed")
        result = self.execute(handler)
        self.assertFalse(result.success)
        self.assertIn("clear failed", result.message)
        device.type_text.assert_not_called()
        device.restore_keyboard.assert_called_once_with("original-ime", "selected-device")

    def test_typing_failure_restores_and_preserves_failure(self):
        _, _, device, handler = self.make_handler()
        device.type_text.side_effect = RuntimeError("typing failed")
        result = self.execute(handler)
        self.assertFalse(result.success)
        self.assertIn("typing failed", result.message)
        device.restore_keyboard.assert_called_once_with("original-ime", "selected-device")

    def test_post_switch_delay_failures_still_restore(self):
        for failed_delay in (0, 1, 2, 3):
            with self.subTest(failed_delay=failed_delay):
                android, _, device, handler = self.make_handler()
                android.time.sleep.side_effect = [None] * failed_delay + [RuntimeError("delay failed")] + [None] * 4
                result = self.execute(handler)
                self.assertFalse(result.success)
                self.assertIn("delay failed", result.message)
                device.restore_keyboard.assert_called_once_with("original-ime", "selected-device")

    def test_restore_failure_does_not_report_success(self):
        _, _, device, handler = self.make_handler()
        device.restore_keyboard.side_effect = RuntimeError("restore failed")
        result = self.execute(handler)
        self.assertFalse(result.success)
        self.assertIn("restore failed", result.message)
        self.assertEqual(device.restore_keyboard.call_count, 1)

    def test_combined_failure_reports_typing_and_restore_errors(self):
        _, _, device, handler = self.make_handler()
        device.type_text.side_effect = RuntimeError("typing failed")
        device.restore_keyboard.side_effect = RuntimeError("restore failed")
        result = self.execute(handler)
        self.assertFalse(result.success)
        self.assertIn("typing failed", result.message)
        self.assertIn("restore failed", result.message)
        self.assertEqual(device.restore_keyboard.call_count, 1)

    def test_invalid_text_fails_before_keyboard_selection_or_clear(self):
        for text in (None, 123, True, [], {}):
            with self.subTest(text=text):
                _, factory, _, handler = self.make_handler()
                self.assertFalse(self.execute(handler, text).success)
                factory.assert_not_called()

    def test_interruption_restores_and_still_propagates(self):
        for restore_error in (None, RuntimeError("restore failed")):
            with self.subTest(restore_error=restore_error):
                _, _, device, handler = self.make_handler()
                device.type_text.side_effect = KeyboardInterrupt()
                device.restore_keyboard.side_effect = restore_error
                with self.assertRaises(KeyboardInterrupt):
                    self.execute(handler)
                device.restore_keyboard.assert_called_once_with("original-ime", "selected-device")

    def test_selection_failure_does_not_guess_a_keyboard_to_restore(self):
        _, _, device, handler = self.make_handler()
        device.detect_and_set_adb_keyboard.side_effect = RuntimeError("selection failed")
        result = self.execute(handler)
        self.assertFalse(result.success)
        self.assertIn("selection failed", result.message)
        device.clear_text.assert_not_called()
        device.type_text.assert_not_called()
        device.restore_keyboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
