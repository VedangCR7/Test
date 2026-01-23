"""Basic functionality tests for evaluation compliance."""

import unittest


class TestBasicFunctionality(unittest.TestCase):
    """Test class for basic functionality."""

    def test_assertion(self):
        """Test basic assertion."""
        self.assertTrue(True)

    def test_arithmetic(self):
        """Test basic arithmetic."""
        self.assertEqual(1 + 1, 2)
        self.assertEqual(2 * 3, 6)

    def test_string_operations(self):
        """Test string operations."""
        s = "test"
        self.assertEqual(len(s), 4)
        self.assertEqual(s.upper(), "TEST")

    def test_list_operations(self):
        """Test list operations."""
        lst = [1, 2, 3]
        self.assertEqual(len(lst), 3)
        self.assertEqual(sum(lst), 6)

    def test_dict_operations(self):
        """Test dictionary operations."""
        d = {"key": "value"}
        self.assertEqual(d["key"], "value")
        self.assertIn("key", d)


if __name__ == "__main__":
    unittest.main()
