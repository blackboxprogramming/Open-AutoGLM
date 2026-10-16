"""Exercise the actual shared parser without model SDKs or device access."""

import contextlib
import io
import unittest

from test_step_outcomes import load_agent


class ActionParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parse = staticmethod(load_agent(False).parse_action)

    def test_supported_literal_actions(self):
        examples = [
            ('do(action="Back")', {"_metadata": "do", "action": "Back"}),
            ('do(action="Tap", element=[500, 250])', {"_metadata": "do", "action": "Tap", "element": [500, 250]}),
            ('do(action="Swipe", start=[0, 1], end=[999, 1000])', {"_metadata": "do", "action": "Swipe", "start": [0, 1], "end": [999, 1000]}),
            ('do(app="Settings", action="Launch")', {"_metadata": "do", "action": "Launch", "app": "Settings"}),
            ('finish()', {"_metadata": "finish"}),
            ('finish(message="ready")', {"_metadata": "finish", "message": "ready"}),
        ]
        for response, expected in examples:
            with self.subTest(response=response):
                self.assertEqual(self.parse(response), expected)

    def test_type_alias_quotes_unicode_and_escapes(self):
        for action in ("Type", "Type_Name"):
            text = 'Alexa’s "road"\nsecond line\tC:\\data'
            response = f"do(text={text!r}, action={action!r})"
            with self.subTest(action=action):
                self.assertEqual(self.parse(response), {
                    "_metadata": "do", "action": "Type", "text": text,
                })

    def test_multiline_call_and_triple_quoted_text(self):
        self.assertEqual(self.parse('  do(\n action="Type",\n text="""line one\nline two""",\n) '), {
            "_metadata": "do", "action": "Type", "text": "line one\nline two",
        })

    def test_wrong_callees_are_rejected(self):
        for response in ('doodle(action="Back")', 'finishgarbage', 'finish_later(message="ready")', 'do.run(action="Back")', '(lambda: 0)(action="Back")'):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_positional_expanded_and_duplicate_arguments_are_rejected(self):
        for response in (
            'do(123, action="Back")', 'do(*[], action="Back")',
            'do(**{"action": "Back"})', 'do(action="Back", action="Home")',
            'finish("ready")', 'finish(message="a", message="b")',
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_metadata_cannot_be_supplied_by_model(self):
        for response in (
            'do(action="Back", _metadata="finish")',
            'do(action="Type", text="hello", _metadata="finish")',
            'finish(message="ready", _metadata="do")',
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_required_strings_and_finish_contract(self):
        for response in (
            'do()', 'do(action=123)', 'do(action="")', 'do(action="  ")',
            'do(action="Type")', 'do(action="Type", text=123)',
            'finish(message=123)', 'finish(action="Back")',
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_no_expression_evaluation_or_multiple_commands(self):
        for response in (
            'do(action=str("Back"))', 'do(action="Back" + "Home")',
            'do(action=[x for x in []])', 'do(action="Back"); finish()',
            'do(action="Back")\nfinish()', '[do(action="Back")]',
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_invalid_type_payload_and_unterminated_calls_are_rejected(self):
        for response in (
            'do(action="Type", text="hello"',
            'do(action="Type", text="unescaped "quotes"")',
            'do(action="Type", text="raw\nnewline")',
            'finish(message="hello"', '',
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.parse(response)

    def test_non_strings_and_complex_or_oversized_output_are_rejected(self):
        values = [None, {}, b'do(action="Back")',
                  'do(action="Type", text="' + 'x' * 65536 + '")',
                  'do(action="Tap", element=[' + ','.join('0' for _ in range(5000)) + '])']
        for response in values:
            with self.subTest(type=type(response).__name__), self.assertRaises(ValueError):
                self.parse(response)

    def test_exact_size_limit_still_accepts_valid_text(self):
        prefix, suffix = 'do(action="Type", text="', '")'
        text = 'x' * (65536 - len(prefix) - len(suffix))
        response = prefix + text + suffix
        self.assertEqual(len(response), 65536)
        self.assertEqual(self.parse(response)["text"], text)

    def test_parser_does_not_echo_payload_into_stdout_or_error(self):
        secret = 'private-test-payload-1729'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.parse(f'do(action="Type", text="{secret}")')
            with self.assertRaises(ValueError) as caught:
                self.parse(f'do(action="Type", text="{secret}"')
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
