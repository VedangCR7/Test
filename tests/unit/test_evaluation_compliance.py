"""Test file for evaluation compliance and basic functionality."""

import pytest


class TestEvaluationCompliance:
    """Test class for evaluation compliance."""

    def test_basic_assertion(self):
        """Test basic assertion functionality."""
        assert True

    def test_arithmetic_operations(self):
        """Test basic arithmetic operations."""
        assert 1 + 1 == 2
        assert 2 * 3 == 6
        assert 10 - 5 == 5

    def test_string_operations(self):
        """Test basic string operations."""
        test_string = "evaluation"
        assert "eval" in test_string
        assert len(test_string) == 10
        assert test_string.upper() == "EVALUATION"

    def test_list_operations(self):
        """Test basic list operations."""
        test_list = [1, 2, 3, 4, 5]
        assert len(test_list) == 5
        assert sum(test_list) == 15
        assert max(test_list) == 5
        assert min(test_list) == 1

    def test_dict_operations(self):
        """Test basic dictionary operations."""
        test_dict = {"key1": "value1", "key2": "value2"}
        assert len(test_dict) == 2
        assert test_dict["key1"] == "value1"
        assert "key1" in test_dict


def test_standalone_function():
    """Standalone test function."""
    data = [1, 2, 3, 4, 5]
    assert len(data) > 0
    assert all(isinstance(x, int) for x in data)


@pytest.fixture
def sample_data():
    """Fixture providing sample test data."""
    return {"numbers": [1, 2, 3], "text": "test"}


def test_with_fixture(sample_data):
    """Test using pytest fixture."""
    assert "numbers" in sample_data
    assert len(sample_data["numbers"]) == 3
    assert sample_data["text"] == "test"


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])
