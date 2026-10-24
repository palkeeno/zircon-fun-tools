"""Behavioral contracts for selection strategies."""
import copy
import unittest
from unittest.mock import patch

from event_selection import select_winners


class SelectionStrategies(unittest.TestCase):
    def test_vote_order_ties_and_input_are_preserved(self):
        entries = {"a": {"vote": 1}, "b": {"vote": 0}, "c": {"vote": 1},
                   "d": {"vote": 0}, "nonvoter": {}}
        event = {"method": "majority", "entries": entries}
        before = copy.deepcopy(event)
        self.assertEqual(select_winners(event), ["a", "c", "b", "d"])
        self.assertEqual(event, before)
        event["method"] = "minority"
        self.assertEqual(select_winners(event), ["a", "c", "b", "d"])

    def test_random_delegates_without_mutating_entries(self):
        event = {"method": "random", "count": 2, "entries": {"a": {}, "b": {}, "c": {}}}
        before = copy.deepcopy(event)
        with patch("event_selection.random.sample", return_value=["c", "a"]) as sample:
            self.assertEqual(select_winners(event), ["c", "a"])
        sample.assert_called_once_with(["a", "b", "c"], 2)
        self.assertEqual(event, before)

    def test_unknown_method_never_falls_back_to_minority(self):
        with self.assertRaises(ValueError):
            select_winners({"method": "unknown", "entries": {"a": {"vote": 0}}})
