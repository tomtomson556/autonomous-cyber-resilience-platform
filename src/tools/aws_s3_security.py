import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from botocore.exceptions import PartialCredentialsError
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_DEFAULT_REGION")
REPORT_PATH = Path("reports/s3_security_report.json")

REQUIRED_ENV_VARS = [
    "AWS_DEFAULT_REGION",
    "BUCKET_NAME",
]

LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def validate_bucket_name(bucket_name: str) -> None:
    bucket_pattern = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")

    if not bucket_pattern.fullmatch(bucket_name):
        raise ValueError(
            "Invalid S3 bucket name. Bucket names must be 3-63 characters long "
            "and may contain lowercase letters, numbers, dots, and hyphens."
        )

    if ".." in bucket_name or ".-" in bucket_name or "-." in bucket_name:
        raise ValueError("Invalid S3 bucket name: invalid dot or hyphen sequence.")

    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", bucket_name):
        raise ValueError("Invalid S3 bucket name: bucket name must not look like IP.")


def get_required_env_var(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")

    return value


def validate_environment() -> str:
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]

    if missing_vars:
        missing = ", ".join(missing_vars)
        raise EnvironmentError(f"Missing required environment variable(s): {missing}")

    bucket_name = get_required_env_var("BUCKET_NAME")
    validate_bucket_name(bucket_name)

    return bucket_name


def create_s3_client():
    """
    Create an S3 client using the AWS default credential provider chain.

    This supports local environment variables, AWS CLI profiles, shared credential
    files, EC2/ECS roles, and future GitHub Actions OIDC-based role assumption.
    """
    session = boto3.Session(region_name=AWS_REGION)
    return session.client("s3")


def get_client_error_code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "Unknown")


def raise_for_critical_s3_error(error: ClientError, check_name: str) -> None:
    error_code = get_client_error_code(error)

    critical_errors = {
        "AccessDenied",
        "AllAccessDisabled",
        "InvalidAccessKeyId",
        "NoSuchBucket",
        "SignatureDoesNotMatch",
    }

    if error_code in critical_errors:
        raise RuntimeError(
            f"{check_name} check failed with critical AWS error: {error_code}"
        ) from error


def check_versioning(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_bucket_versioning(Bucket=bucket_name)
        return response.get("Status") == "Enabled"
    except ClientError as error:
        raise_for_critical_s3_error(error, "versioning")
        LOGGER.warning(
            "Versioning check failed with AWS error: %s",
            get_client_error_code(error),
        )
        return False


def check_encryption(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_bucket_encryption(Bucket=bucket_name)
        rules = response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        approved_algorithms = {"AES256", "aws:kms", "aws:kms:dsse"}

        return any(
            rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm")
            in approved_algorithms
            for rule in rules
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ServerSideEncryptionConfigurationNotFoundError":
            return False

        raise_for_critical_s3_error(error, "encryption")
        LOGGER.warning("Encryption check failed with AWS error: %s", error_code)
        return False


def check_object_lock(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_object_lock_configuration(Bucket=bucket_name)
        configuration = response.get("ObjectLockConfiguration", {})
        return configuration.get("ObjectLockEnabled") == "Enabled"
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ObjectLockConfigurationNotFoundError":
            return False

        raise_for_critical_s3_error(error, "object_lock")
        LOGGER.warning("Object Lock check failed with AWS error: %s", error_code)
        return False


def check_public_access_block(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_public_access_block(Bucket=bucket_name)
        config = response.get("PublicAccessBlockConfiguration", {})
        required_settings = [
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        ]
        return all(config.get(setting) is True for setting in required_settings)
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchPublicAccessBlockConfiguration":
            return False

        raise_for_critical_s3_error(error, "public_access_block")
        LOGGER.warning(
            "Public Access Block check failed with AWS error: %s",
            error_code,
        )
        return False


def check_bucket_policy_not_public(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_bucket_policy_status(Bucket=bucket_name)
        return response.get("PolicyStatus", {}).get("IsPublic") is False
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchBucketPolicy":
            return True

        if error_code == "AccessDenied":
            LOGGER.warning(
                "Bucket policy status check could not be completed due to AccessDenied."
            )
            return False

        raise_for_critical_s3_error(error, "bucket_policy_not_public")
        LOGGER.warning(
            "Bucket policy status check failed with AWS error: %s", error_code
        )
        return False


def _as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def _condition_has_secure_transport_false(condition: dict) -> bool:
    bool_conditions = {}

    for operator, condition_values in condition.items():
        if operator.lower() != "bool" or not isinstance(condition_values, dict):
            continue

        bool_conditions.update(condition_values)

    secure_transport = bool_conditions.get("aws:SecureTransport")

    if isinstance(secure_transport, bool):
        return secure_transport is False

    if isinstance(secure_transport, str):
        return secure_transport.lower() == "false"

    return False


def _action_covers_s3(action) -> bool:
    return any(item in {"s3:*", "*"} for item in _as_list(action))


def _resource_covers_bucket(resource, bucket_name: str) -> bool:
    bucket_arn = f"arn:aws:s3:::{bucket_name}"
    object_arn = f"{bucket_arn}/*"
    resources = set(_as_list(resource))

    return {bucket_arn, object_arn}.issubset(resources) or "*" in resources


def _principal_covers_everyone(principal) -> bool:
    if principal == "*":
        return True

    if isinstance(principal, dict):
        aws_principals = principal.get("AWS")
        return "*" in _as_list(aws_principals)

    return False


def check_secure_transport_policy(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_bucket_policy(Bucket=bucket_name)
        policy = json.loads(response.get("Policy", "{}"))
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchBucketPolicy":
            return False

        if error_code == "AccessDenied":
            LOGGER.warning(
                "Secure transport policy check could not be completed due to AccessDenied."
            )
            return False

        raise_for_critical_s3_error(error, "secure_transport_policy")
        LOGGER.warning("Bucket policy check failed with AWS error: %s", error_code)
        return False
    except json.JSONDecodeError:
        LOGGER.warning(
            "Bucket policy check failed because the policy is not valid JSON."
        )
        return False

    for statement in _as_list(policy.get("Statement")):
        if not isinstance(statement, dict):
            continue

        if statement.get("Effect") != "Deny":
            continue

        if not _action_covers_s3(statement.get("Action")):
            continue

        if not _resource_covers_bucket(statement.get("Resource"), bucket_name):
            continue

        if not _principal_covers_everyone(statement.get("Principal")):
            continue

        if _condition_has_secure_transport_false(statement.get("Condition", {})):
            return True

    return False


def check_bucket_owner_enforced(s3_client, bucket_name: str) -> bool:
    try:
        response = s3_client.get_bucket_ownership_controls(Bucket=bucket_name)
        rules = response.get("OwnershipControls", {}).get("Rules", [])
        return any(
            rule.get("ObjectOwnership") == "BucketOwnerEnforced" for rule in rules
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "OwnershipControlsNotFoundError":
            return False

        if error_code == "AccessDenied":
            LOGGER.warning(
                "Bucket ownership controls check could not be completed due to AccessDenied."
            )
            return False

        raise_for_critical_s3_error(error, "bucket_owner_enforced")
        LOGGER.warning("Ownership controls check failed with AWS error: %s", error_code)
        return False


def build_report(s3_client, bucket_name: str) -> dict:
    checks = {
        "versioning": check_versioning(s3_client, bucket_name),
        "encryption": check_encryption(s3_client, bucket_name),
        "object_lock": check_object_lock(s3_client, bucket_name),
        "public_access_block": check_public_access_block(s3_client, bucket_name),
        "bucket_policy_not_public": check_bucket_policy_not_public(
            s3_client,
            bucket_name,
        ),
        "secure_transport_policy": check_secure_transport_policy(
            s3_client,
            bucket_name,
        ),
        "bucket_owner_enforced": check_bucket_owner_enforced(s3_client, bucket_name),
    }

    overall_status = "SECURE" if all(checks.values()) else "NOT_SECURE"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bucket": bucket_name,
        "checks": {
            check_name: "PASS" if passed else "FAIL"
            for check_name, passed in checks.items()
        },
        "overall_status": overall_status,
    }


def print_report(report: dict) -> None:
    print("\nS3 Security Validation Report")
    print("============================")
    print(f"Bucket: {report['bucket']}\n")

    for check_name, status in report["checks"].items():
        print(f"{check_name}: {status}")

    print("\nOverall Status:", report["overall_status"])


def save_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"\nJSON report written to: {REPORT_PATH}")


def main() -> int:
    configure_logging()

    try:
        bucket_name = validate_environment()
        s3_client = create_s3_client()
        security_report = build_report(s3_client, bucket_name)
        print_report(security_report)
        save_report(security_report)

        if security_report["overall_status"] == "SECURE":
            return 0

        return 1

    except (NoCredentialsError, PartialCredentialsError) as error:
        print(f"\nAWS credential error: {error}")
        return 2
    except BotoCoreError as error:
        print(f"\nAWS client error: {error}")
        return 2
    except Exception as error:
        print(f"\nSecurity validation failed: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
