from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.tools.aws_s3_security import (
    check_encryption,
    check_object_lock,
    check_public_access_block,
    check_versioning,
    validate_bucket_name,
)


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

    assert check_versioning(mock_client) is True


def test_check_versioning_suspended():
    mock_client = MagicMock()
    mock_client.get_bucket_versioning.return_value = {"Status": "Suspended"}

    assert check_versioning(mock_client) is False


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

    assert check_encryption(mock_client) is True


def test_check_encryption_not_configured():
    mock_client = MagicMock()
    mock_client.get_bucket_encryption.side_effect = make_client_error(
        "ServerSideEncryptionConfigurationNotFoundError",
        "GetBucketEncryption",
    )

    assert check_encryption(mock_client) is False


def test_check_object_lock_configured():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.return_value = {
        "ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
        }
    }

    assert check_object_lock(mock_client) is True


def test_check_object_lock_not_configured():
    mock_client = MagicMock()
    mock_client.get_object_lock_configuration.side_effect = make_client_error(
        "ObjectLockConfigurationNotFoundError",
        "GetObjectLockConfiguration",
    )

    assert check_object_lock(mock_client) is False


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

    assert check_public_access_block(mock_client) is True


def test_check_public_access_block_missing():
    mock_client = MagicMock()
    mock_client.get_public_access_block.side_effect = make_client_error(
        "NoSuchPublicAccessBlockConfiguration",
        "GetPublicAccessBlock",
    )

    assert check_public_access_block(mock_client) is False
