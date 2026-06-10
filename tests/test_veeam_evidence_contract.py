from copy import deepcopy

import pytest

from src.tools.veeam_evidence_contract import validate_veeam_collector_profile
from tests.test_veeam_unified_report_adapter import load_veeam_example_report


def make_api_read_only_report() -> dict:
    report = deepcopy(load_veeam_example_report())
    report["data_classification"] = "SANITIZED_OPERATIONAL_EVIDENCE"
    report["collector"] = {
        "name": "veeam_enterprise_manager_read_only_collector",
        "mode": "api_read_only",
    }
    return report


def test_mock_only_profile_remains_valid():
    assert validate_veeam_collector_profile(load_veeam_example_report()) == "mock_only"


def test_api_read_only_profile_is_recognized_at_contract_level():
    assert validate_veeam_collector_profile(make_api_read_only_report()) == "api_read_only"


@pytest.mark.parametrize(
    "mode",
    [
        "api",
        "restore",
        "start",
        "stop",
        "retry",
        "delete",
        "write",
    ],
)
def test_invalid_or_write_like_collector_modes_are_rejected(mode):
    report = make_api_read_only_report()
    report["collector"]["mode"] = mode

    with pytest.raises(ValueError, match="Unsupported Veeam collector mode"):
        validate_veeam_collector_profile(report)


def test_api_read_only_profile_requires_sanitized_operational_classification():
    report = make_api_read_only_report()
    report["data_classification"] = "MOCK_EXAMPLE_ONLY"

    with pytest.raises(ValueError, match="Invalid Veeam api_read_only data classification"):
        validate_veeam_collector_profile(report)


def test_api_read_only_profile_rejects_unapproved_collector_name():
    report = make_api_read_only_report()
    report["collector"]["name"] = "custom_collector"

    with pytest.raises(ValueError, match="Invalid Veeam api_read_only collector profile"):
        validate_veeam_collector_profile(report)
