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

BUCKET_NAME = os.getenv("BUCKET_NAME")
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


def validate_environment() -> None:
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]

    if missing_vars:
        missing = ", ".join(missing_vars)
        raise EnvironmentError(f"Missing required environment variable(s): {missing}")

    if BUCKET_NAME is None:
        raise EnvironmentError("Missing required environment variable: BUCKET_NAME")

    validate_bucket_name(BUCKET_NAME)


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


def check_versioning(s3_client) -> bool:
    try:
        response = s3_client.get_bucket_versioning(Bucket=BUCKET_NAME)
        return response.get("Status") == "Enabled"
    except ClientError as error:
        raise_for_critical_s3_error(error, "versioning")
        LOGGER.warning(
            "Versioning check failed with AWS error: %s",
            get_client_error_code(error),
        )
        return False


def check_encryption(s3_client) -> bool:
    try:
        response = s3_client.get_bucket_encryption(Bucket=BUCKET_NAME)
        rules = response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        return len(rules) > 0
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ServerSideEncryptionConfigurationNotFoundError":
            return False

        raise_for_critical_s3_error(error, "encryption")
        LOGGER.warning("Encryption check failed with AWS error: %s", error_code)
        return False


def check_object_lock(s3_client) -> bool:
    try:
        response = s3_client.get_object_lock_configuration(Bucket=BUCKET_NAME)
        return "ObjectLockConfiguration" in response
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ObjectLockConfigurationNotFoundError":
            return False

        raise_for_critical_s3_error(error, "object_lock")
        LOGGER.warning("Object Lock check failed with AWS error: %s", error_code)
        return False


def check_public_access_block(s3_client) -> bool:
    try:
        response = s3_client.get_public_access_block(Bucket=BUCKET_NAME)
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


def build_report(s3_client) -> dict:
    checks = {
        "versioning": check_versioning(s3_client),
        "encryption": check_encryption(s3_client),
        "object_lock": check_object_lock(s3_client),
        "public_access_block": check_public_access_block(s3_client),
    }

    overall_status = "SECURE" if all(checks.values()) else "NOT_SECURE"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bucket": BUCKET_NAME,
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
        validate_environment()
        s3_client = create_s3_client()
        security_report = build_report(s3_client)
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
