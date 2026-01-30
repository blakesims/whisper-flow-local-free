"""Tests for Phase 3: Config-driven action mapping."""

import unittest
from unittest.mock import patch


class TestGetDestinationForAction(unittest.TestCase):
    """Test the get_destination_for_action function with different pattern types."""

    def test_plain_pattern_matches_any_input_type(self):
        """Plain pattern like 'skool_post' should match any input type."""
        from kb.serve import get_destination_for_action

        mapping = {
            (None, "skool_post"): "Skool",
        }

        # Should match for any input type
        self.assertEqual(get_destination_for_action("meeting", "skool_post", mapping), "Skool")
        self.assertEqual(get_destination_for_action("video", "skool_post", mapping), "Skool")
        self.assertEqual(get_destination_for_action("unknown", "skool_post", mapping), "Skool")

    def test_typed_pattern_matches_specific_input_type(self):
        """Typed pattern like 'meeting.student_guide' should only match that input type."""
        from kb.serve import get_destination_for_action

        mapping = {
            ("meeting", "student_guide"): "Student",
        }

        # Should match only meeting type
        self.assertEqual(get_destination_for_action("meeting", "student_guide", mapping), "Student")
        # Should NOT match other types
        self.assertIsNone(get_destination_for_action("video", "student_guide", mapping))
        self.assertIsNone(get_destination_for_action("zoom", "student_guide", mapping))

    def test_wildcard_pattern_matches_all_input_types(self):
        """Wildcard pattern like '*.summary' should match all input types."""
        from kb.serve import get_destination_for_action

        mapping = {
            ("*", "summary"): "Review",
        }

        # Should match any input type
        self.assertEqual(get_destination_for_action("meeting", "summary", mapping), "Review")
        self.assertEqual(get_destination_for_action("video", "summary", mapping), "Review")
        self.assertEqual(get_destination_for_action("zoom", "summary", mapping), "Review")

    def test_exact_match_priority_over_wildcard(self):
        """Exact typed match should take priority over wildcard."""
        from kb.serve import get_destination_for_action

        mapping = {
            ("meeting", "summary"): "Meeting Review",  # Exact match
            ("*", "summary"): "General Review",         # Wildcard
            (None, "summary"): "Plain Review",          # Plain
        }

        # Exact match wins
        self.assertEqual(get_destination_for_action("meeting", "summary", mapping), "Meeting Review")
        # Wildcard matches others
        self.assertEqual(get_destination_for_action("video", "summary", mapping), "General Review")

    def test_wildcard_priority_over_plain(self):
        """Wildcard match should take priority over plain match."""
        from kb.serve import get_destination_for_action

        mapping = {
            ("*", "summary"): "Wildcard Review",
            (None, "summary"): "Plain Review",
        }

        # Wildcard wins over plain
        self.assertEqual(get_destination_for_action("video", "summary", mapping), "Wildcard Review")

    def test_no_match_returns_none(self):
        """Non-actionable analysis should return None."""
        from kb.serve import get_destination_for_action

        mapping = {
            (None, "skool_post"): "Skool",
        }

        self.assertIsNone(get_destination_for_action("meeting", "unknown_analysis", mapping))
        self.assertIsNone(get_destination_for_action("video", "other_type", mapping))


class TestGetActionMapping(unittest.TestCase):
    """Test parsing of config into structured mapping."""

    @patch('kb.serve._config', {
        "serve": {
            "action_mapping": {
                "skool_post": "Skool",
                "linkedin_post": "LinkedIn",
                "meeting.student_guide": "Student",
                "*.summary": "Review",
            }
        }
    })
    def test_parses_all_pattern_types(self):
        """Config with mixed patterns should be parsed correctly."""
        from kb.serve import get_action_mapping

        mapping = get_action_mapping()

        # Plain patterns
        self.assertEqual(mapping.get((None, "skool_post")), "Skool")
        self.assertEqual(mapping.get((None, "linkedin_post")), "LinkedIn")

        # Typed pattern
        self.assertEqual(mapping.get(("meeting", "student_guide")), "Student")

        # Wildcard pattern
        self.assertEqual(mapping.get(("*", "summary")), "Review")

    @patch('kb.serve._config', {})
    def test_empty_config_returns_empty_mapping(self):
        """Missing serve config should return empty mapping."""
        from kb.serve import get_action_mapping

        mapping = get_action_mapping()
        self.assertEqual(mapping, {})

    @patch('kb.serve._config', {"serve": {}})
    def test_missing_action_mapping_returns_empty(self):
        """Missing action_mapping key should return empty mapping."""
        from kb.serve import get_action_mapping

        mapping = get_action_mapping()
        self.assertEqual(mapping, {})


class TestIntegration(unittest.TestCase):
    """Integration tests for full flow."""

    @patch('kb.serve._config', {
        "serve": {
            "action_mapping": {
                "skool_post": "Skool",
                "meeting.student_guide": "Student Only",
                "*.summary": "Review All",
            }
        }
    })
    def test_full_flow_plain_pattern(self):
        """End-to-end test with plain pattern."""
        from kb.serve import get_action_mapping, get_destination_for_action

        mapping = get_action_mapping()

        # Plain pattern matches any input type
        self.assertEqual(
            get_destination_for_action("video", "skool_post", mapping),
            "Skool"
        )
        self.assertEqual(
            get_destination_for_action("meeting", "skool_post", mapping),
            "Skool"
        )

    @patch('kb.serve._config', {
        "serve": {
            "action_mapping": {
                "skool_post": "Skool",
                "meeting.student_guide": "Student Only",
                "*.summary": "Review All",
            }
        }
    })
    def test_full_flow_typed_pattern(self):
        """End-to-end test with typed pattern."""
        from kb.serve import get_action_mapping, get_destination_for_action

        mapping = get_action_mapping()

        # Typed pattern matches only specific input type
        self.assertEqual(
            get_destination_for_action("meeting", "student_guide", mapping),
            "Student Only"
        )
        # Should NOT match other input types
        self.assertIsNone(
            get_destination_for_action("video", "student_guide", mapping)
        )


if __name__ == "__main__":
    unittest.main()
