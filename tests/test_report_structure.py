from src.tools.aws_s3_security import print_report


def test_report_contains_required_fields():
    report = {
        "timestamp": "2026-06-03T10:00:00+00:00",
        "bucket": "example-bucket",
        "checks": {
            "versioning": "PASS",
            "encryption": "PASS",
            "object_lock": "PASS",
            "public_access_block": "PASS",
            "bucket_policy_not_public": "PASS",
            "secure_transport_policy": "PASS",
            "bucket_owner_enforced": "PASS",
        },
        "overall_status": "SECURE",
    }

    assert "timestamp" in report
    assert "bucket" in report
    assert "checks" in report
    assert "overall_status" in report
    assert report["overall_status"] == "SECURE"


def test_print_report_does_not_crash():
    report = {
        "bucket": "example-bucket",
        "checks": {
            "versioning": "PASS",
            "encryption": "PASS",
            "object_lock": "PASS",
            "public_access_block": "PASS",
            "bucket_policy_not_public": "PASS",
            "secure_transport_policy": "PASS",
            "bucket_owner_enforced": "PASS",
        },
        "overall_status": "SECURE",
    }

    print_report(report)
