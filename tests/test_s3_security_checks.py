from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.tools.aws_s3_security import (
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


def make_client_error(error_code: str, operation_name: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": error_code, "Message": "Test error"}},
        operation_name,
    )


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


def test_check_versioning_enabled():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = {"Status": "Enabled"}

    assert check_versioning(mock_client, TEST_BUCKET) is True


def test_check_versioning_suspended():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = {"Status": "Suspended"}

    assert check_versioning(mock_client, TEST_BUCKET) is False


def test_check_encryption_configured():
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

    assert check_encryption(mock_client, TEST_BUCKET) is True


def test_check_encryption_not_configured():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.side_effect = make_client_error(
        "ServerSideEncryptionConfigurationNotFoundError",
        "GetBucketEncryption",
    )

    assert check_encryption(mock_client, TEST_BUCKET) is False


def test_check_object_lock_configured():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
            "Rule": {
                "DefaultRetention": {
                    "Mode": "GOVERNANCE",
                    "Days": 30,
                }
            },
        }
    }

    assert check_object_lock(mock_client, TEST_BUCKET) is True


def test_check_object_lock_enabled_without_default_retention_passes():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
        }
    }

    assert check_object_lock(mock_client, TEST_BUCKET) is True


def test_check_object_lock_not_configured():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.side_effect = make_client_error(
        "ObjectLockConfigurationNotFoundError",
        "GetObjectLockConfiguration",
    )

    assert check_object_lock(mock_client, TEST_BUCKET) is False


def test_check_public_access_block_fully_enabled():
    mock_client = MagicMock()
    mock_client.get_public_access_block.return_value = {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
    }

    assert check_public_access_block(mock_client, TEST_BUCKET) is True


def test_check_public_access_block_missing():
    mock_client = MagicMock()
    mock_client.get_public_access_block.side_effect = make_client_error(
        "NoSuchPublicAccessBlockConfiguration",
        "GetPublicAccessBlock",
    )

    assert check_public_access_block(mock_client, TEST_BUCKET) is False


def test_check_bucket_policy_not_public_passes_for_non_public_policy_status():
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.return_value = {
        "PolicyStatus": {
            "IsPublic": False,
        }
    }

    assert check_bucket_policy_not_public(mock_client, TEST_BUCKET) is True


def test_check_bucket_policy_not_public_fails_for_public_policy_status():
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.return_value = {
        "PolicyStatus": {
            "IsPublic": True,
        }
    }

    assert check_bucket_policy_not_public(mock_client, TEST_BUCKET) is False


def test_check_bucket_policy_not_public_passes_without_bucket_policy():
    mock_client = MagicMock()
    mock_client.get_bucket_policy_status.side_effect = make_client_error(
        "NoSuchBucketPolicy",
        "GetBucketPolicyStatus",
    )

    assert check_bucket_policy_not_public(mock_client, TEST_BUCKET) is True


def test_check_secure_transport_policy_passes_for_tls_only_deny():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.return_value = {
        "Policy": """
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
    }

    assert check_secure_transport_policy(mock_client, TEST_BUCKET) is True


def test_check_secure_transport_policy_fails_for_limited_principal():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.return_value = {
        "Policy": """
        {
          "Version": "2012-10-17",
          "Statement": [
            {
              "Effect": "Deny",
              "Principal": {
                "AWS": "arn:aws:iam::123456789012:user/example"
              },
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
    }

    assert check_secure_transport_policy(mock_client, TEST_BUCKET) is False


def test_check_secure_transport_policy_fails_without_bucket_policy():
    mock_client = MagicMock()
    mock_client.get_bucket_policy.side_effect = make_client_error(
        "NoSuchBucketPolicy",
        "GetBucketPolicy",
    )

    assert check_secure_transport_policy(mock_client, TEST_BUCKET) is False


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

    assert check_bucket_owner_enforced(mock_client, TEST_BUCKET) is True


def test_check_bucket_owner_enforced_fails_without_ownership_controls():
    mock_client = MagicMock()
    mock_client.get_bucket_ownership_controls.side_effect = make_client_error(
        "OwnershipControlsNotFoundError",
        "GetBucketOwnershipControls",
    )

    assert check_bucket_owner_enforced(mock_client, TEST_BUCKET) is False
