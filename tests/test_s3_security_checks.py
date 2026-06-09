from contextlib import ExitStack
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from src.tools.aws_s3_security import (
    SCHEMA_VERSION,
    build_report,
    check_bucket_owner_enforced,
    check_bucket_policy_not_public,
    check_encryption,
    check_object_lock,
    check_public_access_block,
    check_secure_transport_policy,
    check_versioning,
    validate_bucket_name,
)

TEST_BUCKET = "valid-security-bucket-123"
CHECK_FUNCTIONS = (
    "check_versioning",
    "check_encryption",
    "check_object_lock",
    "check_public_access_block",
    "check_bucket_policy_not_public",
    "check_secure_transport_policy",
    "check_bucket_owner_enforced",
)


def make_client_error(error_code: str, operation_name: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": error_code, "Message": "Test error"}},
        operation_name,
    )


def assert_structured_result(result: dict, expected_status: str) -> None:
    assert result["status"] == expected_status
    assert set(result) == {"status", "reason", "message"}
    assert isinstance(result["message"], str)
    assert result["message"]


def make_result(status: str) -> dict:
    return {
        "status": status,
        "reason": None,
        "message": f"Test {status} result.",
    }


def build_report_with_statuses(**overrides) -> dict:
    results = {check_name: make_result("PASS") for check_name in CHECK_FUNCTIONS}
    results.update(overrides)

    with ExitStack() as stack:
        for check_name, result in results.items():
            stack.enter_context(
                patch(f"src.tools.aws_s3_security.{check_name}", return_value=result)
            )

        return build_report(MagicMock(), TEST_BUCKET)


def tls_only_policy() -> str:
    return """
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Deny",
          "Principal": "*",
          "Action": "s3:*",
          "Resource": [
            "arn:aws:s3:::valid-security-bucket-123",
            "arn:aws:s3:::valid-security-bucket-123/*"
          ],
          "Condition": {
            "Bool": {
              "aws:SecureTransport": "false"
            }
          }
        }
      ]
    }
    """


def test_validate_bucket_name_accepts_valid_name():
    validate_bucket_name("valid-security-bucket-123")


@pytest.mark.parametrize(
    "bucket_name",
    [
        "InvalidUppercase",
        "ab",
        "invalid..dots",
        "invalid.-sequence",
        "192.168.0.1",
        "-starts-with-hyphen",
        "ends-with-hyphen-",
    ],
)
def test_validate_bucket_name_rejects_invalid_names(bucket_name):
    with pytest.raises(ValueError):
        validate_bucket_name(bucket_name)


def test_check_versioning_enabled_passes():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = {"Status": "Enabled"}

    assert_structured_result(check_versioning(mock_client, TEST_BUCKET), "PASS")


@pytest.mark.parametrize("response", [{}, {"Status": "Suspended"}])
def test_check_versioning_not_enabled_fails(response):
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = response

    assert_structured_result(check_versioning(mock_client, TEST_BUCKET), "FAIL")


def test_check_versioning_unexpected_status_is_unknown():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = {"Status": "Unexpected"}

    assert_structured_result(check_versioning(mock_client, TEST_BUCKET), "UNKNOWN")


def test_check_encryption_with_approved_algorithm_passes():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256",
                    }
                }
            ]
        }
    }

    assert_structured_result(check_encryption(mock_client, TEST_BUCKET), "PASS")


def test_check_encryption_without_approved_algorithm_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "unsupported",
                    }
                }
            ]
        }
    }

    assert_structured_result(check_encryption(mock_client, TEST_BUCKET), "FAIL")


def test_check_encryption_incomplete_response_is_unknown():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.return_value = {}

    assert_structured_result(check_encryption(mock_client, TEST_BUCKET), "UNKNOWN")


def test_check_encryption_malformed_rule_is_unknown():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.return_value = {
        "ServerSideEncryptionConfiguration": {"Rules": [{}]}
    }

    assert_structured_result(check_encryption(mock_client, TEST_BUCKET), "UNKNOWN")


def test_check_encryption_not_configured_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.side_effect = make_client_error(
        "ServerSideEncryptionConfigurationNotFoundError",
        "GetBucketEncryption",
    )

    assert_structured_result(check_encryption(mock_client, TEST_BUCKET), "FAIL")


def test_check_object_lock_enabled_passes():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
        }
    }

    assert_structured_result(check_object_lock(mock_client, TEST_BUCKET), "PASS")


def test_check_object_lock_incomplete_response_is_unknown():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {}

    assert_structured_result(check_object_lock(mock_client, TEST_BUCKET), "UNKNOWN")


def test_check_object_lock_unexpected_status_is_unknown():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {"ObjectLockEnabled": "Unexpected"}
    }

    assert_structured_result(check_object_lock(mock_client, TEST_BUCKET), "UNKNOWN")


def test_check_object_lock_not_configured_fails():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.side_effect = make_client_error(
        "ObjectLockConfigurationNotFoundError",
        "GetObjectLockConfiguration",
    )

    assert_structured_result(check_object_lock(mock_client, TEST_BUCKET), "FAIL")


def test_check_public_access_block_fully_enabled_passes():
    mock_client = MagicMock()
    mock_client.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
    }

    assert_structured_result(check_public_access_block(mock_client, TEST_BUCKET), "PASS")


def test_check_public_access_block_disabled_setting_fails():
    mock_client = MagicMock()
    mock_client.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": False,
            "RestrictPublicBuckets": True,
        }
    }

    assert_structured_result(check_public_access_block(mock_client, TEST_BUCKET), "FAIL")


def test_check_public_access_block_incomplete_response_is_unknown():
    mock_client = MagicMock()
    mock_client.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {"BlockPublicAcls": True}
    }

    assert_structured_result(
        check_public_access_block(mock_client, TEST_BUCKET),
        "UNKNOWN",
    )


def test_check_public_access_block_malformed_value_is_unknown():
    mock_client = MagicMock()
    mock_client.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": "true",
            "RestrictPublicBuckets": True,
        }
    }

    assert_structured_result(
        check_public_access_block(mock_client, TEST_BUCKET),
        "UNKNOWN",
    )


def test_check_public_access_block_not_configured_fails():
    mock_client = MagicMock()
    mock_client.get_public_access_block.side_effect = make_client_error(
        "NoSuchPublicAccessBlockConfiguration",
        "GetPublicAccessBlock",
    )

    assert_structured_result(check_public_access_block(mock_client, TEST_BUCKET), "FAIL")


@pytest.mark.parametrize(
    ("is_public", "expected_status"),
    [(False, "PASS"), (True, "FAIL"), (None, "UNKNOWN")],
)
def test_check_bucket_policy_public_status(is_public, expected_status):
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.return_value = {
        "PolicyStatus": {"IsPublic": is_public}
    }

    assert_structured_result(
        check_bucket_policy_not_public(mock_client, TEST_BUCKET),
        expected_status,
    )


def test_check_bucket_policy_not_public_passes_without_bucket_policy():
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.side_effect = make_client_error(
        "NoSuchBucketPolicy",
        "GetBucketPolicyStatus",
    )

    assert_structured_result(
        check_bucket_policy_not_public(mock_client, TEST_BUCKET),
        "PASS",
    )


def test_check_bucket_policy_not_public_raises_for_missing_bucket():
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.side_effect = make_client_error(
        "NoSuchBucket",
        "GetBucketPolicyStatus",
    )

    with pytest.raises(RuntimeError, match="critical AWS error: NoSuchBucket"):
        check_bucket_policy_not_public(mock_client, TEST_BUCKET)


def test_check_secure_transport_policy_enforced_passes():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.return_value = {"Policy": tls_only_policy()}

    assert_structured_result(
        check_secure_transport_policy(mock_client, TEST_BUCKET),
        "PASS",
    )


def test_check_secure_transport_policy_not_enforced_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.return_value = {
        "Policy": '{"Version": "2012-10-17", "Statement": []}'
    }

    assert_structured_result(
        check_secure_transport_policy(mock_client, TEST_BUCKET),
        "FAIL",
    )


def test_check_secure_transport_policy_missing_policy_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.side_effect = make_client_error(
        "NoSuchBucketPolicy",
        "GetBucketPolicy",
    )

    assert_structured_result(
        check_secure_transport_policy(mock_client, TEST_BUCKET),
        "FAIL",
    )


@pytest.mark.parametrize(
    "policy",
    [
        "not-json",
        "{}",
        '{"Statement": "not-a-valid-statement"}',
        '{"Statement": ["not-a-valid-statement"]}',
        '{"Statement": [{"Effect": "Deny", "Action": {}, "Resource": "*"}]}',
        """
        {
          "Statement": [{
            "Effect": "Deny",
            "Principal": 42,
            "Action": "s3:*",
            "Resource": "*"
          }]
        }
        """,
    ],
)
def test_check_secure_transport_policy_malformed_evidence_is_unknown(policy):
    mock_client = MagicMock()
    mock_client.get_bucket_policy.return_value = {"Policy": policy}

    assert_structured_result(
        check_secure_transport_policy(mock_client, TEST_BUCKET),
        "UNKNOWN",
    )


def test_check_bucket_owner_enforced_passes_for_disabled_acls():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.return_value = {
        "OwnershipControls": {
            "Rules": [
                {
                    "ObjectOwnership": "BucketOwnerEnforced",
                }
            ]
        }
    }

    assert_structured_result(
        check_bucket_owner_enforced(mock_client, TEST_BUCKET),
        "PASS",
    )


def test_check_bucket_owner_enforced_other_rule_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.return_value = {
        "OwnershipControls": {
            "Rules": [
                {
                    "ObjectOwnership": "BucketOwnerPreferred",
                }
            ]
        }
    }

    assert_structured_result(
        check_bucket_owner_enforced(mock_client, TEST_BUCKET),
        "FAIL",
    )


def test_check_bucket_owner_enforced_incomplete_response_is_unknown():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.return_value = {}

    assert_structured_result(
        check_bucket_owner_enforced(mock_client, TEST_BUCKET),
        "UNKNOWN",
    )


def test_check_bucket_owner_enforced_unexpected_rule_is_unknown():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.return_value = {
        "OwnershipControls": {"Rules": [{"ObjectOwnership": "Unexpected"}]}
    }

    assert_structured_result(
        check_bucket_owner_enforced(mock_client, TEST_BUCKET),
        "UNKNOWN",
    )


def test_check_bucket_owner_enforced_missing_controls_fails():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.side_effect = make_client_error(
        "OwnershipControlsNotFoundError",
        "GetBucketOwnershipControls",
    )

    assert_structured_result(
        check_bucket_owner_enforced(mock_client, TEST_BUCKET),
        "FAIL",
    )


@pytest.mark.parametrize(
    ("check_function", "client_method"),
    [
        (check_versioning, "get_bucket_versioning"),
        (check_encryption, "get_bucket_encryption"),
        (check_object_lock, "get_object_lock_configuration"),
        (check_public_access_block, "get_public_access_block"),
        (check_bucket_policy_not_public, "get_bucket_policy_status"),
        (check_secure_transport_policy, "get_bucket_policy"),
        (check_bucket_owner_enforced, "get_bucket_ownership_controls"),
    ],
)
def test_access_denied_is_unknown_for_individual_checks(check_function, client_method):
    mock_client = MagicMock()
    getattr(mock_client, client_method).side_effect = make_client_error(
        "AccessDenied",
        client_method,
    )

    result = check_function(mock_client, TEST_BUCKET)

    assert_structured_result(result, "UNKNOWN")
    assert result["reason"] == "AccessDenied"


def test_invalid_credentials_remain_execution_error():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.side_effect = make_client_error(
        "ExpiredToken",
        "GetBucketVersioning",
    )

    with pytest.raises(RuntimeError, match="critical AWS error: ExpiredToken"):
        check_versioning(mock_client, TEST_BUCKET)


def test_build_report_is_incomplete_for_unknown_without_fail():
    report = build_report_with_statuses(check_versioning=make_result("UNKNOWN"))

    assert report["overall_status"] == "INCOMPLETE"


def test_build_report_fail_takes_precedence_over_unknown():
    report = build_report_with_statuses(
        check_versioning=make_result("FAIL"),
        check_encryption=make_result("UNKNOWN"),
    )

    assert report["overall_status"] == "INSECURE"


def test_build_report_is_secure_when_all_checks_pass():
    report = build_report_with_statuses()

    assert report["overall_status"] == "SECURE"
    assert report["schema_version"] == SCHEMA_VERSION
    assert set(report) == {
        "schema_version",
        "timestamp",
        "bucket",
        "checks",
        "overall_status",
    }
    assert all(
        set(result) == {"status", "reason", "message"}
        for result in report["checks"].values()
    )
