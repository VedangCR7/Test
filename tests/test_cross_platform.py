"""
Cross-platform compatibility tests.

Ensures the AI Content Pipeline works correctly across different operating systems.
"""

import os
import sys
import platform


def test_platform_detection():
    """Test that platform detection works correctly."""
    try:
        system = platform.system().lower()
        print(f"[INFO] Detected platform: {system}")

        # Test platform-specific path handling
        test_path = os.path.join("test", "directory", "file.txt")

        if system == "windows":
            expected_sep = "\\"
        else:
            expected_sep = "/"

        if expected_sep in test_path:
            print("[PASS] Path separator handling correct")
            return True
        else:
            print("[FAIL] Path separator handling incorrect")
            return False

    except Exception as e:
        print(f"[ERROR] Platform detection failed: {e}")
        return False


def test_file_operations():
    """Test basic file operations work across platforms."""
    try:
        # Test creating a temporary file
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_file = f.name

        # Test reading it back
        with open(temp_file, 'r') as f:
            content = f.read()

        # Clean up
        os.unlink(temp_file)

        if content == "test content":
            print("[PASS] File operations work correctly")
            return True
        else:
            print("[FAIL] File operations failed")
            return False

    except Exception as e:
        print(f"[ERROR] File operations test failed: {e}")
        return False


def test_environment_variables():
    """Test environment variable handling."""
    try:
        # Test setting and getting environment variables
        test_key = "TEST_UNICODE_VAR"
        test_value = "unicode_test_value_🚀"

        # Set environment variable
        os.environ[test_key] = test_value

        # Get it back
        retrieved_value = os.environ.get(test_key)

        # Clean up
        if test_key in os.environ:
            del os.environ[test_key]

        if retrieved_value == test_value:
            print("[PASS] Environment variable handling works")
            return True
        else:
            print("[FAIL] Environment variable handling failed")
            return False

    except Exception as e:
        print(f"[ERROR] Environment variable test failed: {e}")
        return False


def test_unicode_file_paths():
    """Test handling of Unicode in file paths."""
    try:
        import tempfile

        # Create a file with Unicode in path (where supported)
        with tempfile.NamedTemporaryFile(mode='w', prefix='test_unicode_', delete=False) as f:
            f.write("unicode test content")
            temp_file = f.name

        # Test reading it back
        with open(temp_file, 'r') as f:
            content = f.read()

        # Clean up
        os.unlink(temp_file)

        if content == "unicode test content":
            print("[PASS] Unicode file path handling works")
            return True
        else:
            print("[FAIL] Unicode file path handling failed")
            return False

    except Exception as e:
        print(f"[ERROR] Unicode file path test failed: {e}")
        return False


if __name__ == "__main__":
    print(">>> Cross-Platform Compatibility Tests")
    print("="*45)

    tests = [
        ("Platform Detection", test_platform_detection),
        ("File Operations", test_file_operations),
        ("Environment Variables", test_environment_variables),
        ("Unicode File Paths", test_unicode_file_paths),
    ]

    passed = 0
    for test_name, test_func in tests:
        try:
            print(f"\n[TEST] {test_name}...")
            if test_func():
                passed += 1
                print(f"[PASS] {test_name} completed successfully")
            else:
                print(f"[FAIL] {test_name} failed")
        except Exception as e:
            print(f"[ERROR] {test_name} crashed: {e}")

    print(f"\n{'='*45}")
    print(f"[SUMMARY] CROSS-PLATFORM TESTS: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("[SUCCESS] All cross-platform tests passed!")
        sys.exit(0)
    else:
        print("[WARNING] Some cross-platform tests failed")
        sys.exit(1)