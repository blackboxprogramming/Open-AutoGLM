"""Offline outcome regressions; model and device boundaries are replaced.

Loads the actual agent and parser sources without installing optional SDKs.
These tests do not establish live inference, device control or task completion.
"""

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_source(name, path, dependencies):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {name: loaded, **dependencies}):
        spec.loader.exec_module(loaded)
    return loaded


def load_agent(ios):
    handler = load_source(
        "offline_handler",
        "phone_agent/actions/handler.py",
        {
            "phone_agent.config.timing": module("timing", TIMING_CONFIG=None),
            "phone_agent.device_factory": module("devices", get_device_factory=Mock()),
        },
    )
    builder = types.SimpleNamespace(
        create_system_message=lambda text: {"role": "system", "content": text},
        build_screen_info=lambda app: app,
        create_user_message=lambda **kw: {"role": "user", "content": kw},
        create_assistant_message=lambda text: {"role": "assistant", "content": text},
        remove_images_from_message=lambda message: message,
    )
    dependencies = {
        "phone_agent.actions": module("actions", ActionHandler=object),
        "phone_agent.actions.handler": handler,
        "phone_agent.actions.handler_ios": module("ios_actions", IOSActionHandler=object),
        "phone_agent.config": module(
            "config",
            get_system_prompt=lambda lang: "system",
            get_messages=lambda lang: {
                "thinking": "thinking", "action": "action",
                "task_completed": "Task completed", "done": "done",
            },
        ),
        "phone_agent.model": module("model", ModelClient=object, ModelConfig=object),
        "phone_agent.model.client": module("client", MessageBuilder=builder),
        "phone_agent.device_factory": module("devices", get_device_factory=Mock()),
        "phone_agent.xctest": module(
            "xctest", XCTestConnection=object, get_current_app=Mock(), get_screenshot=Mock()
        ),
    }
    source = "phone_agent/agent_ios.py" if ios else "phone_agent/agent.py"
    return load_source("offline_ios" if ios else "offline_android", source, dependencies)


class StepOutcomeTests(unittest.TestCase):
    def make_agent(self, ios, action='do(action="Back")', verbose=False):
        loaded = load_agent(ios)
        cls = loaded.IOSPhoneAgent if ios else loaded.PhoneAgent
        agent = cls.__new__(cls)
        agent.agent_config = types.SimpleNamespace(
            device_id="offline", lang="en", system_prompt="system",
            verbose=verbose, wda_url="http://localhost:8100", session_id="offline",
            max_steps=1,
        )
        agent.model_client = Mock()
        agent.model_client.request.return_value = types.SimpleNamespace(
            action=action, thinking="test reasoning"
        )
        agent.action_handler = Mock()
        agent.action_handler.execute.return_value = types.SimpleNamespace(
            success=True, should_finish=False, message=None
        )
        agent._context = []
        agent._step_count = 0
        screen = types.SimpleNamespace(base64_data="offline", width=100, height=100)
        if ios:
            loaded.get_screenshot.return_value = screen
            loaded.get_current_app.return_value = "offline"
        else:
            device = loaded.get_device_factory.return_value
            device.get_screenshot.return_value = screen
            device.get_current_app.return_value = "offline"
        return loaded, agent

    def test_malformed_output_is_terminal_failure_without_execution(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios, action="not an action")
                result = agent.step("test")
                self.assertFalse(result.success)
                self.assertTrue(result.finished)
                self.assertIsNone(result.action)
                self.assertIn("Action parse error:", result.message)
                self.assertEqual(result.thinking, "test reasoning")
                agent.action_handler.execute.assert_not_called()

    def test_execution_exception_is_failure_without_second_execution(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios)
                agent.action_handler.execute.side_effect = [
                    RuntimeError("device disconnected"),
                    types.SimpleNamespace(success=True, should_finish=True, message="wrong"),
                ]
                result = agent.step("test")
                self.assertFalse(result.success)
                self.assertTrue(result.finished)
                self.assertEqual(result.message, "Action execution error: device disconnected")
                self.assertEqual(result.action["action"], "Back")
                self.assertEqual(agent.action_handler.execute.call_count, 1)

    def test_malformed_envelopes_never_execute_actions_on_either_platform(self):
        for ios in (False, True):
            for action in (
                'doodle(action="Back")', 'finishgarbage',
                'do(action="Back", _metadata="finish")',
                'do(action="Type", text="hello", _metadata="finish")',
                'do(action="Back", action="Home")',
                'do(123, action="Back")',
            ):
                with self.subTest(ios=ios, action=action):
                    _, agent = self.make_agent(ios, action=action)
                    result = agent.step("test")
                    self.assertFalse(result.success)
                    self.assertTrue(result.finished)
                    self.assertIsNone(result.action)
                    self.assertIn("Action parse error:", result.message)
                    agent.action_handler.execute.assert_not_called()

    def test_failed_terminal_action_has_no_completion_banner(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios, verbose=True)
                agent.action_handler.execute.return_value = types.SimpleNamespace(
                    success=False, should_finish=True, message="cancelled"
                )
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = agent.step("test")
                self.assertFalse(result.success)
                self.assertTrue(result.finished)
                self.assertNotIn("Task completed", output.getvalue())

    def test_explicit_finish_preserves_success_and_banner(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios, action='finish(message="ready")', verbose=True)
                agent.action_handler.execute.return_value = types.SimpleNamespace(
                    success=True, should_finish=True, message="ready"
                )
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = agent.step("test")
                self.assertTrue(result.success)
                self.assertTrue(result.finished)
                self.assertEqual(result.message, "ready")
                self.assertIn("Task completed", output.getvalue())

    def test_successful_nonterminal_action_continues(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios)
                result = agent.step("test")
                self.assertTrue(result.success)
                self.assertFalse(result.finished)
                self.assertEqual(agent.step_count, 1)
                self.assertEqual(agent.context[-1]["role"], "assistant")

    def test_model_failure_never_executes_action(self):
        for ios in (False, True):
            with self.subTest(ios=ios):
                _, agent = self.make_agent(ios)
                agent.model_client.request.side_effect = RuntimeError("offline")
                result = agent.step("test")
                self.assertFalse(result.success)
                self.assertTrue(result.finished)
                self.assertEqual(result.message, "Model error: offline")
                agent.action_handler.execute.assert_not_called()

    def test_run_does_not_default_failed_result_to_success(self):
        for ios in (False, True):
            for terminal_step in (1, 2):
                with self.subTest(ios=ios, terminal_step=terminal_step):
                    loaded, agent = self.make_agent(ios)
                    agent.agent_config.max_steps = 2
                    failed = loaded.StepResult(False, True, None, "", None)
                    pending = loaded.StepResult(True, False, None, "", None)
                    agent._execute_step = Mock(
                        side_effect=[failed] if terminal_step == 1 else [pending, failed]
                    )
                    self.assertEqual(agent.run("test"), "Task failed")


if __name__ == "__main__":
    unittest.main()
