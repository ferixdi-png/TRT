#!/usr/bin/env python3
"""
Unit tests for telemetry contract - ensures log_callback_rejected signature compatibility.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from app.telemetry import log_callback_rejected, generate_cid
from app.telemetry.logging_contract import ReasonCode


def test_log_callback_rejected_signature():
    """Test that log_callback_rejected accepts all expected parameters."""
    cid = generate_cid()
    
    # Test 1: Minimal call (backward compatible)
    try:
        log_callback_rejected()
        assert True, "Should accept no parameters"
    except TypeError as e:
        pytest.fail(f"Should accept no parameters: {e}")
    
    # Test 2: With reason_detail (new parameter)
    try:
        log_callback_rejected(
            callback_data="test:data",
            reason_code=ReasonCode.UNKNOWN_CALLBACK,
            reason_detail="Test detail",
            cid=cid
        )
        assert True, "Should accept reason_detail"
    except TypeError as e:
        pytest.fail(f"Should accept reason_detail: {e}")
    
    # Test 3: With all parameters
    try:
        log_callback_rejected(
            callback_data="test:data",
            reason="OLD_REASON",
            reason_detail="Test detail",
            reason_code=ReasonCode.INTERNAL_ERROR,
            error_type="TestError",
            error_message="Test error message",
            cid=cid
        )
        assert True, "Should accept all parameters"
    except TypeError as e:
        pytest.fail(f"Should accept all parameters: {e}")
    
    # Test 4: With extra (backward compatible)
    try:
        log_callback_rejected(
            callback_data="test:data",
            reason_code=ReasonCode.VALIDATION_FAIL,
            cid=cid,
            extra_field="extra_value"
        )
        assert True, "Should accept extra parameters"
    except TypeError as e:
        pytest.fail(f"Should accept extra parameters: {e}")


def test_log_callback_rejected_never_raises():
    """Test that log_callback_rejected never raises exceptions."""
    # Even with invalid parameters, should not raise
    try:
        log_callback_rejected(
            callback_data=None,
            reason_code=None,
            reason_detail=None,
            cid=None
        )
        assert True, "Should not raise even with None values"
    except Exception as e:
        pytest.fail(f"Should not raise exceptions: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

