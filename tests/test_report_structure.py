from src.tools.aws_s3_security import print_report


def pass_result():
    return {
        "status": "PASS",
        "reason": None,
        "message": "The check passed.",
    }


def test_report_contains_required_fields():
    report = {
        "schema_version": "s3-security-report/v1",
        "timestamp": "2026-06-03T10:00:00+00:00",
        "bucket": "example-bucket",
        "checks": {
            "versioning": pass_result(),
            "encryption": pass_result(),
            "object_lock": pass_result(),
            "public_access_block": pass_result(),
            "bucket_policy_not_public": pass_result(),
            "secure_transport_policy": pass_result(),
            "bucket_owner_enforced": pass_result(),
        },
        "overall_status": "SECURE",
    }

    assert set(report) == {
        "schema_version",
        "timestamp",
        "bucket",
        "checks",
        "overall_status",
    }
    assert report["schema_version"] == "s3-security-report/v1"
    assert report["overall_status"] == "SECURE"
    assert all(
        set(result) == {"status", "reason", "message"}
        for result in report["checks"].values()
    )


def test_print_report_does_not_crash():
    report = {
        "schema_version": "s3-security-report/v1",
        "bucket": "example-bucket",
        "checks": {
            "versioning": pass_result(),
            "encryption": pass_result(),
            "object_lock": pass_result(),
            "public_access_block": pass_result(),
            "bucket_policy_not_public": pass_result(),
            "secure_transport_policy": pass_result(),
            "bucket_owner_enforced": pass_result(),
        },
        "overall_status": "SECURE",
    }

    print_report(report)
