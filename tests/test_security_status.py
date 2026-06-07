import pytest

from src.tools.security_status import calculate_overall_status


def test_only_pass_results_are_secure():
    assert calculate_overall_status(["PASS", "PASS"]) == "SECURE"


def test_at_least_one_fail_result_is_insecure():
    assert calculate_overall_status(["PASS", "FAIL", "PASS"]) == "INSECURE"


def test_unknown_without_fail_is_incomplete():
    assert calculate_overall_status(["PASS", "UNKNOWN", "PASS"]) == "INCOMPLETE"


def test_fail_takes_precedence_over_unknown():
    assert calculate_overall_status(["PASS", "UNKNOWN", "FAIL"]) == "INSECURE"


def test_empty_check_statuses_are_rejected():
    with pytest.raises(ValueError, match="At least one check status is required"):
        calculate_overall_status([])


def test_invalid_check_status_is_rejected():
    with pytest.raises(ValueError, match="Invalid check status: NOT_SECURE"):
        calculate_overall_status(["PASS", "NOT_SECURE"])
