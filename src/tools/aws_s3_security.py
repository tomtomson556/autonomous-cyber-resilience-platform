import boto3

BUCKET_NAME = "cyber-resilience-backup-lab-tom-2026"

s3 = boto3.client("s3")


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


checks = {
    "Versioning": check_versioning(),
    "Encryption": check_encryption(),
    "Object Lock": check_object_lock(),
    "Public Access Block": check_public_access_block(),
}

print("\nS3 Security Validation Report")
print("============================")
print(f"Bucket: {BUCKET_NAME}\n")

for check_name, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"{check_name}: {status}")

overall_status = "SECURE" if all(checks.values()) else "NOT SECURE"

print("\nOverall Status:", overall_status)
