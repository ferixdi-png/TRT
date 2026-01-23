from app.pricing.ssot_catalog import validate_pricing_schema_consistency


def test_pricing_schema_consistency():
    issues = validate_pricing_schema_consistency()
    assert issues == {}, f"Pricing schema issues detected: {issues}"
