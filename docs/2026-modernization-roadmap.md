# 2026 Modernization Roadmap

This project is now aligned around a stronger cyber-resilience posture for S3-backed backup validation. The current upgrade path focuses on controls that produce evidence, reduce ransomware blast radius, and can be automated in CI or scheduled validation jobs.

## Implemented baseline

- Validate S3 versioning.
- Validate approved server-side encryption algorithms.
- Validate S3 Object Lock capability.
- Validate full S3 Block Public Access.
- Validate bucket policy status is not public.
- Validate an explicit TLS-only bucket policy.
- Validate Object Ownership is `BucketOwnerEnforced`, which disables ACLs.
- Provision matching Terraform controls for TLS-only access and bucket-owner-enforced object ownership.

## Next high-value phases

1. Add KMS-backed encryption evidence.

   Extend Terraform with a customer-managed KMS key, key rotation, bucket keys, and least-privilege key policy. Extend the validator to report whether encryption uses `aws:kms` or `aws:kms:dsse` and which key protects the bucket.

2. Add recovery and ransomware-resilience scoring.

   Add checks for cross-region replication, lifecycle rules for noncurrent versions, restore drills, and report fields that distinguish prevention, detection, and recovery controls.

3. Add AWS-native detection coverage.

   Add optional validation for CloudTrail S3 data events, GuardDuty S3 protection or Malware Protection for S3, AWS Config managed rules, and IAM Access Analyzer findings.

4. Add CI supply-chain evidence.

   Generate SBOM output, run dependency vulnerability scanning, upload test coverage, and add pinned GitHub Action permissions per job.

5. Add an operator-facing interface.

   Build a small dashboard that can compare reports over time, show drift, and export executive and technical summaries from the same machine-readable report.

## Apply notes

Object Lock is intentionally strong. Once enabled on a bucket, it cannot be disabled, and versioning cannot be suspended. Terraform Object Lock provisioning is intentionally left for a separate, explicitly reviewed change because enabling it on an existing bucket can require replacement or irreversible configuration changes.

