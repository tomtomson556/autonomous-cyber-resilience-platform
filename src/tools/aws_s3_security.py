import json
import os
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.getenv("BUCKET_NAME")
REPORT_PATH = "reports/s3_security_report.json"

REQUIRED_ENV_VARS = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "BUCKET_NAME",
]


def validate_environment():
    missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]

    if missing_vars:
        missing = ", ".join(missing_vars)
        raise EnvironmentError(f"Missing required environment variable(s): {missing}")


s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION"),
)


def check_versioning():
    response = s3.get_bucket_versioning(Bucket=BUCKET_NAME)
    return response.get("Status") == "Enabled"


def check_encryption():
    try:
        response = s3.get_bucket_encryption(Bucket=BUCKET_NAME)
        rules = response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        return len(rules) > 0
    except Exception:
        return False


def check_object_lock():
    try:
        response = s3.get_object_lock_configuration(Bucket=BUCKET_NAME)
        return "ObjectLockConfiguration" in response
    except Exception:
        return False


def check_public_access_block():
    try:
        response = s3.get_public_access_block(Bucket=BUCKET_NAME)
        config = response.get("PublicAccessBlockConfiguration", {})
        required = [
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        ]
        return all(config.get(item) is True for item in required)
    except Exception:
        return False


def build_report():
    checks = {
        "versioning": check_versioning(),
        "encryption": check_encryption(),
        "object_lock": check_object_lock(),
        "public_access_block": check_public_access_block(),
    }

    overall_status = "SECURE" if all(checks.values()) else "NOT_SECURE"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bucket": BUCKET_NAME,
        "checks": {
            check_name: "PASS" if passed else "FAIL"
            for check_name, passed in checks.items()
        },
        "overall_status": overall_status,
    }

    return report


def print_report(report):
    print("\nS3 Security Validation Report")
    print("============================")
    print(f"Bucket: {report['bucket']}\n")

    for check_name, status in report["checks"].items():
        print(f"{check_name}: {status}")

    print("\nOverall Status:", report["overall_status"])


def save_report(report):
    os.makedirs("reports", exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(f"\nJSON report written to: {REPORT_PATH}")


if __name__ == "__main__":
    validate_environment()
    security_report = build_report()
    print_report(security_report)
    save_report(security_report)
