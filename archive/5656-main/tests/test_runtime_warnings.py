"""
P0: Test that fails build on RuntimeWarning "coroutine was never awaited"

This test ensures that any code that creates a coroutine without awaiting it
will fail the build, preventing silent bugs.
"""

import warnings
import pytest
import sys
import asyncio


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


@pytest.mark.asyncio
async def test_storage_init_no_asyncio_run():
    """
    P0: Test that storage initialization doesn't use asyncio.run() in async context.
    
    This test verifies that get_storage() and init_pg_storage() work correctly
    in async context without triggering "asyncio.run() cannot be called from a running event loop".
    """
    import os
    import warnings
    
    # Set up test environment (no DATABASE_URL to avoid real connection)
    original_db_url = os.environ.get('DATABASE_URL')
    try:
        # Remove DATABASE_URL to test FileStorage path
        if 'DATABASE_URL' in os.environ:
            del os.environ['DATABASE_URL']
        
        # Import after env setup
        from app.storage import get_storage
        
        # This should not raise "asyncio.run() cannot be called from a running event loop"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("error", RuntimeWarning)
            
            # Call get_storage from async context
            storage = get_storage()
            
            # Check for RuntimeWarning about asyncio.run()
            runtime_warnings = [warning for warning in w if issubclass(warning.category, RuntimeWarning)]
            for warning in runtime_warnings:
                if "asyncio.run()" in str(warning.message) or "running event loop" in str(warning.message):
                    pytest.fail(
                        f"RuntimeWarning about asyncio.run() in async context: {warning.message}\n"
                        f"Location: {warning.filename}:{warning.lineno}\n"
                        f"This indicates storage initialization is using asyncio.run() in runtime."
                    )
            
            assert storage is not None, "Storage should be initialized"
    finally:
        # Restore original DATABASE_URL
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url


if __name__ == "__main__":
    # Run with: python -W error::RuntimeWarning tests/test_runtime_warnings.py
    pytest.main([__file__, "-v", "-W", "error::RuntimeWarning"])

