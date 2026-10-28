import unittest

import jmespath
from jmespath import exceptions


class TestMatches(unittest.TestCase):

    def test_r1_requires_exactly_two_string_arguments(self):
        with self.assertRaises(exceptions.ArityError) as caught:
            jmespath.search('matches(@)', 'abc')
        self.assertEqual(
            str(caught.exception),
            'Expected 2 arguments for function matches(), received 1')

        with self.assertRaises(exceptions.ArityError) as caught:
            jmespath.search('matches(@, @, @)', 'abc')
        self.assertEqual(
            str(caught.exception),
            'Expected 2 arguments for function matches(), received 3')

        with self.assertRaises(exceptions.JMESPathTypeError):
            jmespath.search('matches(@, `pattern`)', 42)

        with self.assertRaises(exceptions.JMESPathTypeError):
            jmespath.search('matches(`subject`, @)', 42)

    def test_r2_returns_true_for_a_match_and_false_for_no_match(self):
        self.assertIs(
            jmespath.search('matches(`abc`, `b`)', {}),
            True)
        self.assertIs(
            jmespath.search('matches(`abc`, `z`)', {}),
            False)

    def test_r3_uses_python_re_search_semantics(self):
        self.assertIs(
            jmespath.search('matches(`abc`, `b`)', {}),
            True)
        self.assertIs(
            jmespath.search('matches(`abc`, `^a`)', {}),
            True)
        self.assertIs(
            jmespath.search('matches(`abc`, `^b`)', {}),
            False)
        self.assertIs(
            jmespath.search('matches(`abc123`, `.*`)', {}),
            True)
        self.assertIs(
            jmespath.search('matches(`abc123`, `[0-9]`)', {}),
            True)
        self.assertIs(
            jmespath.search('matches(`abc123`, `123$`)', {}),
            True)
        self.assertIs(
            jmespath.search(r"matches(`a+b`, `\\+`)", {}),
            True)

    def test_r4_invalid_regex_raises_jmespath_type_error(self):
        with self.assertRaises(exceptions.JMESPathTypeError) as caught:
            jmespath.search(r"matches(`abc`, `[`)", {})

        message = str(caught.exception)
        self.assertIn('matches()', message)
        self.assertIn('value: [', message)

    def test_r5_can_be_used_as_a_filter_predicate(self):
        data = {
            'people': [
                {'name': 'alice'},
                {'name': 'bob'},
            ],
        }

        self.assertEqual(
            jmespath.search('people[?matches(name, `^a`)].name', data),
            ['alice'])

    def test_r6_type_error_message_includes_value_type_and_expected_types(self):
        with self.assertRaises(exceptions.JMESPathTypeError) as caught:
            jmespath.search('matches(@, `pattern`)', 42)

        message = str(caught.exception)
        self.assertIn('matches()', message)
        self.assertIn('invalid type for value: 42', message)
        self.assertIn("expected one of: ['string']", message)
        self.assertIn('received: "number"', message)
