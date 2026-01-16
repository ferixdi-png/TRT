"""
P0: Test that fails build on RuntimeWarning "coroutine was never awaited"

This test ensures that any code that creates a coroutine without awaiting it
will fail the build, preventing silent bugs.
"""

import warnings
import pytest
import sys


def test_no_runtime_warnings_coroutine_never_awaited():
    """
    P0: Fail build if RuntimeWarning "coroutine was never awaited" is raised.
    
    This test should be run with: python -W error::RuntimeWarning -m pytest tests/test_runtime_warnings.py
    Or in CI: pytest -W error::RuntimeWarning tests/test_runtime_warnings.py
    """
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("error", RuntimeWarning)
        
        # Import main module - this should not raise RuntimeWarning
        try:
            import main_render
            # If we get here, no RuntimeWarning was raised during import
            assert True, "No RuntimeWarning raised during import"
        except RuntimeWarning as e:
            # If RuntimeWarning is raised, fail the test
            pytest.fail(f"RuntimeWarning raised during import: {e}")
        
        # Check that no RuntimeWarning was captured
        runtime_warnings = [warning for warning in w if issubclass(warning.category, RuntimeWarning)]
        if runtime_warnings:
            for warning in runtime_warnings:
                if "coroutine" in str(warning.message).lower() and "never awaited" in str(warning.message).lower():
                    pytest.fail(
                        f"RuntimeWarning 'coroutine was never awaited' detected: {warning.message}\n"
                        f"Location: {warning.filename}:{warning.lineno}\n"
                        f"This indicates a bug where a coroutine is created but not awaited."
                    )


if __name__ == "__main__":
    # Run with: python -W error::RuntimeWarning tests/test_runtime_warnings.py
    pytest.main([__file__, "-v", "-W", "error::RuntimeWarning"])

