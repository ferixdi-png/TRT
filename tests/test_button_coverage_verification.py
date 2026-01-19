from scripts.verify_button_coverage import main


def test_verify_button_coverage_passes():
    assert main() == 0
