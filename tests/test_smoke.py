"""
Smoke test: basic functionality without real API keys.
Validates core components can be imported and initialized.
"""
import os
import pytest

# Set test mode
os.environ['TEST_MODE'] = 'true'
os.environ['KIE_STUB'] = 'true'
os.environ['DRY_RUN'] = '1'


def test_imports():
    """Test that core modules can be imported."""
    from app.kie.generator import KieGenerator
    from app.payments.integration import generate_with_payment
    from app.payments.charges import get_charge_manager
    from app.kie.builder import load_source_of_truth
    assert True


def test_generator_init():
    """Test generator can be initialized."""
    from app.kie.generator import KieGenerator
    generator = KieGenerator()
    assert generator is not None


def test_source_of_truth_loads():
    """Test source of truth can be loaded."""
    from app.kie.builder import load_source_of_truth
    sot = load_source_of_truth()
    assert isinstance(sot, dict)
    assert 'models' in sot


def test_charge_manager_init():
    """Test charge manager can be initialized."""
    from app.payments.charges import get_charge_manager
    cm = get_charge_manager()
    assert cm is not None


def test_config_loads():
    """Test config can be loaded."""
    from app.utils.config import get_config
    config = get_config()
    assert config is not None


def test_healthcheck():
    """Test healthcheck module."""
    from app.utils.healthcheck import get_health_state, set_health_state
    set_health_state("test", "smoke", ready=True)
    state = get_health_state()
    assert state is not None
    assert 'status' in state


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
