"""Run real handlers with isolated device and clock boundaries."""

import types
import unittest
from unittest.mock import Mock

from test_step_outcomes import load_source, module


def load_handlers():
    factory = Mock()
    android = load_source("bounded_android", "phone_agent/actions/handler.py", {
        "phone_agent.config.timing": module("timing", TIMING_CONFIG=None),
        "phone_agent.device_factory": module("devices", get_device_factory=factory),
    })
    commands = {name: Mock() for name in (
        "back", "double_tap", "home", "launch_app", "long_press", "swipe", "tap",
        "clear_text", "hide_keyboard", "type_text",
    )}
    ios = load_source("bounded_ios", "phone_agent/actions/handler_ios.py", {
        "phone_agent.actions.handler": android,
        "phone_agent.xctest": module("xctest", **commands),
        "phone_agent.xctest.input": module("input", **commands),
    })
    for loaded in (android, ios):
        loaded.time = types.SimpleNamespace(sleep=Mock())
    return android, ios, factory, commands


class ActionBoundsTests(unittest.TestCase):
    def handlers(self):
        android, ios, factory, commands = load_handlers()
        for loaded, handler, controls in (
            (android, android.ActionHandler, [factory]),
            (ios, ios.IOSActionHandler, list(commands.values())),
        ):
            confirmation = Mock(return_value=False)
            instance = handler(confirmation_callback=confirmation, takeover_callback=Mock())
            yield loaded, instance, controls, confirmation

    def assert_no_control(self, controls):
        for control in controls:
            self.assertEqual(control.mock_calls, [])

    def test_invalid_points_fail_before_device_control_or_confirmation(self):
        for point in ([-1, 0], [1000, 0], [0, 1000], [True, 1], [1.5, 2],
                      [0], [0, 1, 2], "12", {0: 1, 1: 2}, None, []):
            for loaded, handler, controls, confirmation in self.handlers():
                for name in ("Tap", "Double Tap", "Long Press"):
                    with self.subTest(platform=loaded.__name__, name=name, point=point):
                        result = handler.execute({
                            "_metadata": "do", "action": name, "element": point,
                            "message": "sensitive",
                        }, 1080, 1920)
                        self.assertFalse(result.success)
                        self.assert_no_control(controls)
                        confirmation.assert_not_called()

    def test_invalid_swipe_endpoint_fails_before_device_control(self):
        for bad_field in ("start", "end"):
            for point in ([-1, 0], [1000, 0], [True, 2], [1], "12"):
                for loaded, handler, controls, _ in self.handlers():
                    with self.subTest(platform=loaded.__name__, field=bad_field, point=point):
                        action = {"_metadata": "do", "action": "Swipe", "start": [0, 0], "end": [999, 999]}
                        action[bad_field] = point
                        self.assertFalse(handler.execute(action, 1080, 1920).success)
                        self.assert_no_control(controls)

    def test_invalid_screen_dimensions_fail_before_device_control(self):
        for width, height in ((0, 1920), (-1, 1920), (1080, 0), (True, 1920),
                              (1080.0, 1920), (1080, "1920")):
            for loaded, handler, controls, _ in self.handlers():
                with self.subTest(platform=loaded.__name__, width=width, height=height):
                    result = handler.execute({"_metadata": "do", "action": "Tap", "element": [500, 500]}, width, height)
                    self.assertFalse(result.success)
                    self.assert_no_control(controls)

    def test_valid_coordinate_conversion_preserves_pixel_mapping(self):
        for _, handler, _, _ in self.handlers():
            for point, size, expected in (
                ([0, 0], (1080, 1920), (0, 0)),
                ([500, 250], (1080, 1920), (540, 480)),
                ([999, 999], (1080, 1920), (1078, 1918)),
                ([999, 999], (1, 1), (0, 0)),
                ([290, 0], (100, 1000), (29, 0)),
            ):
                with self.subTest(point=point, size=size):
                    self.assertEqual(handler._convert_relative_to_absolute(point, *size), expected)

    def test_valid_tap_reaches_each_platform_with_expected_pixels(self):
        android, ios, factory, commands = load_handlers()
        self.assertTrue(android.ActionHandler().execute({
            "_metadata": "do", "action": "Tap", "element": [500, 250],
        }, 1080, 1920).success)
        factory.return_value.tap.assert_called_once_with(540, 480, None)
        self.assertTrue(ios.IOSActionHandler().execute({
            "_metadata": "do", "action": "Tap", "element": [500, 250],
        }, 1080, 1920).success)
        commands["tap"].assert_called_once_with(540, 480, wda_url="http://localhost:8100", session_id=None)

    def test_valid_swipe_reaches_each_platform_with_expected_pixels(self):
        android, ios, factory, commands = load_handlers()
        action = {"_metadata": "do", "action": "Swipe", "start": [0, 0], "end": [999, 999]}
        self.assertTrue(android.ActionHandler().execute(action, 1080, 1920).success)
        factory.return_value.swipe.assert_called_once_with(0, 0, 1078, 1918, device_id=None)
        self.assertTrue(ios.IOSActionHandler().execute(action, 1080, 1920).success)
        commands["swipe"].assert_called_once_with(0, 0, 1078, 1918, wda_url="http://localhost:8100", session_id=None)

    def test_invalid_wait_never_sleeps(self):
        for duration in ("nonsense", "nan seconds", "inf seconds", "-1 seconds",
                         "30.0001 seconds", "100000 seconds", "1secondsseconds",
                         "", None, True, 1, [], "1 minute"):
            for loaded, handler, controls, _ in self.handlers():
                with self.subTest(platform=loaded.__name__, duration=duration):
                    result = handler.execute({"_metadata": "do", "action": "Wait", "duration": duration}, 1080, 1920)
                    self.assertFalse(result.success)
                    loaded.time.sleep.assert_not_called()
                    self.assert_no_control(controls)

    def test_valid_wait_values_and_default(self):
        for duration, expected in (("0 seconds", 0.0), ("1.5 seconds", 1.5),
                                   ("30 seconds", 30.0), (" 0.25 ", 0.25), ("1e-3 seconds", 0.001)):
            for loaded, handler, controls, _ in self.handlers():
                with self.subTest(platform=loaded.__name__, duration=duration):
                    result = handler.execute({"_metadata": "do", "action": "Wait", "duration": duration}, 1080, 1920)
                    self.assertTrue(result.success)
                    loaded.time.sleep.assert_called_once_with(expected)
                    self.assert_no_control(controls)
        for loaded, handler, _, _ in self.handlers():
            self.assertTrue(handler.execute({"_metadata": "do", "action": "Wait"}, 1080, 1920).success)
            loaded.time.sleep.assert_called_once_with(1.0)

    def test_valid_sensitive_tap_cancellation_still_prevents_control(self):
        for _, handler, controls, confirmation in self.handlers():
            result = handler.execute({"_metadata": "do", "action": "Tap", "element": [500, 500], "message": "sensitive"}, 1080, 1920)
            self.assertFalse(result.success)
            self.assertTrue(result.should_finish)
            confirmation.assert_called_once_with("sensitive")
            self.assert_no_control(controls)


if __name__ == "__main__":
    unittest.main()
