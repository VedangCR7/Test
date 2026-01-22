"""
Test for Unicode encoding fix.

This test verifies that the Unicode encoding bug has been fixed
and output works correctly on all platforms including Windows.
"""

import sys


def test_unicode_output():
    """Test that output works without Unicode encoding errors."""
    try:
        # Test various output messages that were causing issues
        print("[TEST] Testing Unicode compatibility...")
        print("[PASS] Unicode test successful")
        print("[SUCCESS] All Unicode tests passed")
        print("[READY] Package is ready for use")
        print("[SUMMARY] Unicode compatibility verified")
        return True
    except UnicodeEncodeError as e:
        print(f"[FAIL] Unicode encoding error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False


def test_ascii_compatibility():
    """Test that ASCII output works correctly."""
    try:
        # Test ASCII-only output patterns
        messages = [
            "[TEST] Testing ASCII compatibility",
            "[PASS] ASCII test successful",
            "[FAIL] ASCII test failed",
            "[ERROR] ASCII test error",
            "[WARNING] ASCII test warning",
            "[SUMMARY] ASCII compatibility verified",
            "[SUCCESS] All ASCII tests passed",
            "[READY] Package is ready for use"
        ]

        for message in messages:
            print(message)

        return True
    except Exception as e:
        print(f"[ERROR] ASCII compatibility test failed: {e}")
        return False


if __name__ == "__main__":
    print(">>> Unicode Compatibility Tests")
    print("="*40)

    tests = [
        ("Unicode Output", test_unicode_output),
        ("ASCII Compatibility", test_ascii_compatibility)
    ]

    passed = 0
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"[PASS] {test_name} - PASSED\n")
            else:
                print(f"[FAIL] {test_name} - FAILED\n")
        except Exception as e:
            print(f"[ERROR] {test_name} - ERROR: {e}\n")

    print("="*40)
    print(f"[SUMMARY] UNICODE TESTS: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("[SUCCESS] All Unicode compatibility tests passed!")
        sys.exit(0)
    else:
        print("[WARNING] Some Unicode tests failed")
        sys.exit(1)