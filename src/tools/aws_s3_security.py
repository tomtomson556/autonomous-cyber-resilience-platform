import argparse
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

if __package__:
    from src.tools.security_status import calculate_overall_status
else:
    from security_status import calculate_overall_status

load_dotenv()

AWS_REGION = os.getenv("AWS_DEFAULT_REGION")
REPORT_PATH = Path("reports/s3_security_report.json")
SCHEMA_VERSION = "s3-security-report/v1"

REQUIRED_ENV_VARS = [
    "AWS_DEFAULT_REGION",
    "BUCKET_NAME",
]

LOGGER = logging.getLogger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate security controls for an AWS S3 backup bucket.",
    )
    return parser.parse_args(argv)


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


def check_result(status: str, reason: str | None, message: str) -> dict:
    return {
        "status": status,
        "reason": reason,
        "message": message,
    }


def raise_for_critical_s3_error(error: ClientError, check_name: str) -> None:
    error_code = get_client_error_code(error)

    critical_errors = {
        "AllAccessDisabled",
        "ExpiredToken",
        "InvalidAccessKeyId",
        "InvalidToken",
        "NoSuchBucket",
        "SignatureDoesNotMatch",
        "TokenRefreshRequired",
        "UnrecognizedClientException",
    }

    if error_code in critical_errors:
        raise RuntimeError(
            f"{check_name} check failed with critical AWS error: {error_code}"
        ) from error


def unknown_aws_error(error_code: str, check_name: str) -> dict:
    LOGGER.warning("%s check failed with AWS error: %s", check_name, error_code)
    return check_result(
        "UNKNOWN",
        error_code,
        f"The {check_name} check could not be evaluated.",
    )


def check_versioning(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_bucket_versioning(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The bucket versioning response is malformed.",
            )

        status = response.get("Status")

        if status == "Enabled":
            return check_result("PASS", None, "Bucket versioning is enabled.")

        if status in {None, "Suspended"}:
            return check_result(
                "FAIL",
                "VersioningNotEnabled",
                "Bucket versioning is not enabled.",
            )

        return check_result(
            "UNKNOWN",
            "UnexpectedVersioningStatus",
            "The bucket versioning status could not be interpreted.",
        )
    except ClientError as error:
        raise_for_critical_s3_error(error, "versioning")
        return unknown_aws_error(get_client_error_code(error), "versioning")


def check_encryption(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_bucket_encryption(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The bucket encryption response is malformed.",
            )

        configuration = response.get("ServerSideEncryptionConfiguration")
        if not isinstance(configuration, dict):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket encryption response is incomplete.",
            )

        rules = configuration.get("Rules")
        approved_algorithms = {"AES256", "aws:kms", "aws:kms:dsse"}

        if not isinstance(rules, list) or not rules:
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket encryption response is incomplete.",
            )

        algorithms = []
        for rule in rules:
            if not isinstance(rule, dict):
                return check_result(
                    "UNKNOWN",
                    "MalformedResponse",
                    "The bucket encryption response is malformed.",
                )

            default_encryption = rule.get("ApplyServerSideEncryptionByDefault")
            if not isinstance(default_encryption, dict) or not isinstance(
                default_encryption.get("SSEAlgorithm"), str
            ):
                return check_result(
                    "UNKNOWN",
                    "MalformedResponse",
                    "The bucket encryption response is malformed.",
                )

            algorithms.append(default_encryption["SSEAlgorithm"])

        if any(algorithm in approved_algorithms for algorithm in algorithms):
            return check_result(
                "PASS",
                None,
                "Bucket default encryption uses an approved algorithm.",
            )

        return check_result(
            "FAIL",
            "ApprovedEncryptionNotConfigured",
            "Bucket default encryption does not use an approved algorithm.",
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ServerSideEncryptionConfigurationNotFoundError":
            return check_result(
                "FAIL",
                error_code,
                "Bucket default encryption is not configured.",
            )

        raise_for_critical_s3_error(error, "encryption")
        return unknown_aws_error(error_code, "encryption")


def check_object_lock(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_object_lock_configuration(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The S3 Object Lock response is malformed.",
            )

        configuration = response.get("ObjectLockConfiguration")
        if not isinstance(configuration, dict):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The S3 Object Lock response is incomplete.",
            )

        status = configuration.get("ObjectLockEnabled")

        if status == "Enabled":
            return check_result("PASS", None, "S3 Object Lock is enabled.")

        if status is None:
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The S3 Object Lock response is incomplete.",
            )

        return check_result(
            "UNKNOWN",
            "UnexpectedObjectLockStatus",
            "The S3 Object Lock status could not be interpreted.",
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "ObjectLockConfigurationNotFoundError":
            return check_result(
                "FAIL",
                error_code,
                "S3 Object Lock is not configured.",
            )

        raise_for_critical_s3_error(error, "object_lock")
        return unknown_aws_error(error_code, "object_lock")


def check_public_access_block(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_public_access_block(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The Public Access Block response is malformed.",
            )

        config = response.get("PublicAccessBlockConfiguration")
        required_settings = [
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        ]

        if not isinstance(config, dict) or any(
            setting not in config for setting in required_settings
        ):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The Public Access Block response is incomplete.",
            )

        if any(not isinstance(config[setting], bool) for setting in required_settings):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The Public Access Block response is malformed.",
            )

        if all(config[setting] is True for setting in required_settings):
            return check_result(
                "PASS",
                None,
                "All Public Access Block settings are enabled.",
            )

        return check_result(
            "FAIL",
            "PublicAccessBlockNotFullyEnabled",
            "One or more Public Access Block settings are not enabled.",
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchPublicAccessBlockConfiguration":
            return check_result(
                "FAIL",
                error_code,
                "Public Access Block is not configured.",
            )

        raise_for_critical_s3_error(error, "public_access_block")
        return unknown_aws_error(error_code, "public_access_block")


def check_bucket_policy_not_public(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_bucket_policy_status(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The bucket policy status response is malformed.",
            )

        policy_status = response.get("PolicyStatus")
        if not isinstance(policy_status, dict):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket policy status response is incomplete.",
            )

        is_public = policy_status.get("IsPublic")

        if is_public is False:
            return check_result("PASS", None, "The bucket policy is not public.")

        if is_public is True:
            return check_result(
                "FAIL",
                "BucketPolicyIsPublic",
                "The bucket policy is public.",
            )

        return check_result(
            "UNKNOWN",
            "IncompleteResponse",
            "The bucket policy status response is incomplete.",
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchBucketPolicy":
            return check_result(
                "PASS",
                error_code,
                "The bucket has no bucket policy that could be public.",
            )

        raise_for_critical_s3_error(error, "bucket_policy_not_public")
        return unknown_aws_error(error_code, "bucket_policy_not_public")


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


def _is_string_or_string_list(value) -> bool:
    return isinstance(value, str) or (
        isinstance(value, list) and all(isinstance(item, str) for item in value)
    )


def _policy_statement_is_malformed(statement: dict) -> bool:
    if statement.get("Effect") not in {"Allow", "Deny"}:
        return True

    for field_pair in (("Action", "NotAction"), ("Resource", "NotResource")):
        present_fields = [field for field in field_pair if field in statement]
        if len(present_fields) != 1 or not _is_string_or_string_list(
            statement[present_fields[0]]
        ):
            return True

    principal_fields = [
        field for field in ("Principal", "NotPrincipal") if field in statement
    ]
    if len(principal_fields) != 1:
        return True

    principal = statement[principal_fields[0]]
    if isinstance(principal, dict):
        if not principal or any(
            not _is_string_or_string_list(value) for value in principal.values()
        ):
            return True
    elif not isinstance(principal, str):
        return True

    condition = statement.get("Condition")
    if condition is not None and (
        not isinstance(condition, dict)
        or any(
            not isinstance(operator, str) or not isinstance(values, dict)
            for operator, values in condition.items()
        )
    ):
        return True

    return False


def check_secure_transport_policy(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_bucket_policy(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The bucket policy response is malformed.",
            )

        policy_document = response.get("Policy")

        if not isinstance(policy_document, str):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket policy response is incomplete.",
            )

        policy = json.loads(policy_document)
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "NoSuchBucketPolicy":
            return check_result(
                "FAIL",
                error_code,
                "The bucket has no policy enforcing secure transport.",
            )

        raise_for_critical_s3_error(error, "secure_transport_policy")
        return unknown_aws_error(error_code, "secure_transport_policy")
    except json.JSONDecodeError:
        return check_result(
            "UNKNOWN",
            "MalformedPolicy",
            "The bucket policy is not valid JSON.",
        )

    if not isinstance(policy, dict) or not isinstance(
        policy.get("Statement"), (dict, list)
    ):
        return check_result(
            "UNKNOWN",
            "MalformedPolicy",
            "The bucket policy structure could not be interpreted.",
        )

    for statement in _as_list(policy.get("Statement")):
        if not isinstance(statement, dict):
            return check_result(
                "UNKNOWN",
                "MalformedPolicy",
                "The bucket policy structure could not be interpreted.",
            )

        if _policy_statement_is_malformed(statement):
            return check_result(
                "UNKNOWN",
                "MalformedPolicy",
                "The bucket policy structure could not be interpreted.",
            )

        try:
            if statement.get("Effect") != "Deny":
                continue

            if not _action_covers_s3(statement.get("Action")):
                continue

            if not _resource_covers_bucket(statement.get("Resource"), bucket_name):
                continue

            if not _principal_covers_everyone(statement.get("Principal")):
                continue

            if _condition_has_secure_transport_false(statement.get("Condition", {})):
                return check_result(
                    "PASS",
                    None,
                    "The bucket policy enforces secure transport.",
                )
        except (AttributeError, TypeError):
            return check_result(
                "UNKNOWN",
                "MalformedPolicy",
                "The bucket policy structure could not be interpreted.",
            )

    return check_result(
        "FAIL",
        "SecureTransportNotEnforced",
        "The bucket policy does not enforce secure transport.",
    )


def check_bucket_owner_enforced(s3_client, bucket_name: str) -> dict:
    try:
        response = s3_client.get_bucket_ownership_controls(Bucket=bucket_name)
        if not isinstance(response, dict):
            return check_result(
                "UNKNOWN",
                "MalformedResponse",
                "The bucket ownership controls response is malformed.",
            )

        ownership_controls = response.get("OwnershipControls")
        if not isinstance(ownership_controls, dict):
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket ownership controls response is incomplete.",
            )

        rules = ownership_controls.get("Rules")

        if not isinstance(rules, list) or not rules:
            return check_result(
                "UNKNOWN",
                "IncompleteResponse",
                "The bucket ownership controls response is incomplete.",
            )

        ownership_values = []
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(
                rule.get("ObjectOwnership"), str
            ):
                return check_result(
                    "UNKNOWN",
                    "MalformedResponse",
                    "The bucket ownership controls response is malformed.",
                )

            ownership_values.append(rule["ObjectOwnership"])

        if "BucketOwnerEnforced" in ownership_values:
            return check_result(
                "PASS",
                None,
                "Bucket owner enforced object ownership is configured.",
            )

        known_ownership_values = {"BucketOwnerPreferred", "ObjectWriter"}
        if any(value not in known_ownership_values for value in ownership_values):
            return check_result(
                "UNKNOWN",
                "UnexpectedObjectOwnership",
                "The bucket object ownership value could not be interpreted.",
            )

        return check_result(
            "FAIL",
            "BucketOwnerEnforcedNotConfigured",
            "Bucket owner enforced object ownership is not configured.",
        )
    except ClientError as error:
        error_code = get_client_error_code(error)

        if error_code == "OwnershipControlsNotFoundError":
            return check_result(
                "FAIL",
                error_code,
                "Bucket ownership controls are not configured.",
            )

        raise_for_critical_s3_error(error, "bucket_owner_enforced")
        return unknown_aws_error(error_code, "bucket_owner_enforced")


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

    check_statuses = [result["status"] for result in checks.values()]
    overall_status = calculate_overall_status(check_statuses)

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bucket": bucket_name,
        "checks": checks,
        "overall_status": overall_status,
    }


def print_report(report: dict) -> None:
    print("\nS3 Security Validation Report")
    print("============================")
    print(f"Bucket: {report['bucket']}\n")

    for check_name, result in report["checks"].items():
        status = result["status"] if isinstance(result, dict) else result
        print(f"{check_name}: {status}")

    print("\nOverall Status:", report["overall_status"])


def save_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"\nJSON report written to: {REPORT_PATH}")


def main(argv=None) -> int:
    parse_args(argv)
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
