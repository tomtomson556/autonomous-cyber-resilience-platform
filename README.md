# Autonomous Cyber-Resilience Platform

![CI](https://github.com/tomtomson556/autonomous-cyber-resilience-platform/actions/workflows/ci.yml/badge.svg)

AI-assisted cyber resilience and backup security validation platform for hybrid cloud environments.

## Overview

This project demonstrates an enterprise-style security validation workflow for cloud backup infrastructure using:

* AWS S3
* Python
* boto3
* IAM
* S3 Object Lock
* Encryption Validation
* Security Automation
* Terraform
* GitHub Actions OIDC

The platform validates whether backup storage is configured according to modern cloud security best practices.

---

## Architecture

```mermaid
flowchart LR
    A[Python Security Validator] --> B[boto3 AWS SDK]
    B --> C[AWS S3 Backup Lab Bucket]

    C --> D[Bucket Versioning]
    C --> E[Server-side Encryption]
    C --> F[Object Lock Capability]
    C --> G[Public Access Block]
    C --> K[TLS-only Bucket Policy]
    C --> L[Bucket Owner Enforced]

    H[Terraform Infrastructure as Code] --> C
    I[IAM Least Privilege Users] --> B
    J[JSON Security Report] --> M[Local Reports Directory]

    N[GitHub Actions OIDC] --> O[Read-only AWS Validator Role]
    O --> B
```

---

## Current Features

### S3 Security Validation

Automated validation of:

* Bucket Versioning
* Server-side Encryption
* Object Lock capability
* Public Access Block configuration
* Bucket policy public exposure status
* TLS-only bucket policy enforcement
* S3 Object Ownership with ACLs disabled

### AWS Integration

* IAM-based authentication
* AWS CLI integration
* boto3 SDK automation
* AWS default credential provider chain support
* GitHub Actions OIDC authentication for read-only cloud validation

### Security Controls

* Immutable-storage-ready configuration
* Encrypted object storage
* Public exposure prevention
* TLS-only data access
* ACL-free bucket ownership enforcement
* Least-privilege IAM access
* Short-lived AWS credentials through GitHub Actions OIDC
* Machine-readable JSON security report output

### Infrastructure as Code with Terraform

The project includes Terraform-based infrastructure deployment for the S3 lab environment.

Terraform provisions:

* S3 bucket
* Bucket versioning
* Server-side encryption
* Public access blocking
* S3 Object Lock enabled at bucket creation
* Object Lock default retention in Governance mode
* Bucket owner enforced object ownership
* TLS-only bucket policy
* Resource tagging
* Terraform outputs for bucket name, ARN, and region

This demonstrates reproducible infrastructure deployment and cloud security automation using Infrastructure as Code.

### OIDC-based AWS Security Validation

The project includes a manual GitHub Actions workflow that validates AWS S3 security controls using OpenID Connect.

This workflow:

* Runs manually through `workflow_dispatch`
* Assumes a dedicated read-only AWS IAM role
* Uses short-lived AWS credentials
* Does not require AWS access keys in GitHub Secrets
* Runs the Python S3 security validator against the lab bucket
* Uploads the generated JSON security report as a GitHub Actions artifact

The AWS role used by this workflow is restricted to the repository and the `main` branch.

---

## Technologies

* Python 3
* AWS S3
* boto3
* IAM
* AWS CLI
* Terraform
* Git
* GitHub
* Infrastructure as Code
* pytest
* Ruff
* GitHub Actions
* GitHub Actions OIDC
* Dependabot

---

## Project Structure

```text
.
├── .github/workflows/              # GitHub Actions CI and AWS validation workflows
├── docs/                           # Documentation and example reports
├── infrastructure/terraform/       # Terraform infrastructure definitions
├── reports/                        # Local generated reports, ignored by Git
├── src/tools/                      # Python security validation tools
├── tests/                          # Unit tests with mocked AWS clients
├── .env.example                    # Example environment configuration
├── .gitignore                      # Excludes secrets, state files, and runtime artifacts
├── README.md                       # Project documentation
├── SECURITY.md                     # Security policy
├── pytest.ini                      # Pytest configuration
└── requirements.txt                # Python dependencies
```

Key components:

* `src/tools/aws_s3_security.py` runs the S3 security validation.
* `infrastructure/terraform/` defines the S3 lab infrastructure as code.
* `.github/workflows/ci.yml` runs Python, test, linting, and Terraform validation.
* `.github/workflows/aws-security-validation.yml` runs the OIDC-based AWS S3 security validation workflow.
* `docs/example_s3_security_report.json` shows a safe example output.
* `reports/` stores local runtime reports and is intentionally excluded from GitHub.
* `tests/` contains unit tests using mocked boto3 clients.

---

## Local Setup

Clone the repository:

```bash
git clone https://github.com/tomtomson556/autonomous-cyber-resilience-platform.git
cd autonomous-cyber-resilience-platform
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

Then configure your local `.env` file:

```text
AWS_DEFAULT_REGION=eu-central-1
AWS_PROFILE=cyber-resilience-bot
BUCKET_NAME=your_s3_bucket_name_here
```

AWS credentials are resolved through the AWS default credential provider chain. For local lab usage, prefer an
AWS CLI profile backed by AWS SSO or another temporary-credential source. GitHub Actions cloud validation uses
OIDC and does not require AWS access keys in GitHub Secrets.

Long-lived environment-variable access keys are not recommended. If they are used temporarily for local lab
testing, keep them outside Git, rotate them after use, and prefer replacing them with AWS SSO or profile-based
temporary credentials:

```text
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_access_key_here
```

Run the S3 security validator:

```bash
python src/tools/aws_s3_security.py
```

---

## Testing

Run the unit tests locally:

```bash
pytest
```

Run Ruff linting locally:

```bash
ruff check src tests
```

The test suite includes unit tests for:

* S3 bucket name validation
* Bucket versioning checks
* Server-side encryption checks
* Object Lock checks
* Public Access Block checks
* Bucket policy exposure checks
* Secure transport policy checks
* Bucket ownership enforcement checks
* JSON report structure

AWS API behavior is tested with mocked boto3 clients, so unit tests do not require live AWS access.

The project also includes a GitHub Actions CI workflow that automatically validates:

* Python dependency installation
* Ruff linting
* Python syntax compilation
* Unit tests
* Terraform formatting
* Terraform validation

---

## Dependency Governance

This project uses Dependabot to keep dependencies up to date across Python packages, GitHub Actions,
and Terraform providers.

Automated dependency updates are configured for:

* Python dependencies via `pip`
* GitHub Actions
* Terraform providers

AWS SDK related Python packages are grouped into a single Dependabot update group:

* `boto3`
* `botocore`
* `s3transfer`

Terraform AWS provider major version updates are intentionally ignored by Dependabot. Major provider
upgrades can introduce breaking changes and should be tested separately with `terraform plan` before
being merged.

This keeps routine patch and minor updates automated while maintaining controlled governance for
infrastructure-critical major upgrades.

---

## Example Validation Output

```text
S3 Security Validation Report
============================
Bucket: cyber-resilience-objectlock-lab-tom-2026

versioning: PASS
encryption: PASS
object_lock: PASS
public_access_block: PASS
bucket_policy_not_public: PASS
secure_transport_policy: PASS
bucket_owner_enforced: PASS

Overall Status: SECURE
```

---

## Security Report Output

The validator also generates a machine-readable JSON report for downstream automation,
documentation, or future incident-response workflows.

Generated reports are written locally to:

```text
reports/s3_security_report.json
```

Runtime reports are excluded from GitHub via `.gitignore`.

A safe example report is included here:

```text
docs/example_s3_security_report.json
```

Example JSON report:

```json
{
  "timestamp": "2026-06-03T10:00:00+00:00",
  "bucket": "cyber-resilience-backup-lab-example",
  "checks": {
    "versioning": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    },
    "encryption": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    },
    "object_lock": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    },
    "public_access_block": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    },
    "bucket_policy_not_public": {
      "status": "PASS",
      "reason": null,
      "message": "The bucket policy is not public."
    },
    "secure_transport_policy": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    },
    "bucket_owner_enforced": {
      "status": "PASS",
      "reason": null,
      "message": "The check passed."
    }
  },
  "overall_status": "SECURE"
}
```

Each check includes a status, an optional reason, and a short explanation.
`UNKNOWN` means that a check could not be evaluated with sufficient confidence,
for example because of `AccessDenied` or missing evidence. `INCOMPLETE` means
that no check returned `FAIL`, but at least one check returned `UNKNOWN`.

---

## Terraform Deployment

Terraform configuration is located in:

```text
infrastructure/terraform/
```

Before running Terraform commands, switch into the Terraform directory:

```bash
cd infrastructure/terraform
```

### Configure variables

The Terraform-managed S3 bucket name is configured through a required variable.

Create a local Terraform variables file from the example:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Then edit `terraform.tfvars` and set a globally unique S3 bucket name:

```hcl
bucket_name = "your-globally-unique-s3-bucket-name"
```

The local `terraform.tfvars` file is excluded from GitHub via `.gitignore` and should not be committed.

### Validate configuration

```bash
terraform validate
```

### Preview infrastructure changes

```bash
terraform plan
```

Alternatively, pass the bucket name explicitly without creating a local `terraform.tfvars` file:

```bash
terraform plan -var="bucket_name=your-globally-unique-s3-bucket-name"
```

### Deploy infrastructure

```bash
terraform apply
```

Alternatively, pass the bucket name explicitly during deployment:

```bash
terraform apply -var="bucket_name=your-globally-unique-s3-bucket-name"
```

### Show outputs

```bash
terraform output
```

Example outputs:

```text
bucket_name   = "cyber-resilience-objectlock-lab-tom-2026"
bucket_arn    = "arn:aws:s3:::cyber-resilience-objectlock-lab-tom-2026"
bucket_region = "eu-central-1"
```

State files and local variable files are intentionally excluded from GitHub via `.gitignore`.

The Terraform-managed lab bucket is created with Object Lock enabled at bucket creation time. The default retention configuration uses Governance mode with a 1-day retention period for safe lab testing.

---

## GitHub Actions OIDC Validation

The repository includes a manual AWS validation workflow:

```text
.github/workflows/aws-security-validation.yml
```

This workflow uses GitHub Actions OIDC to assume a dedicated AWS IAM role:

```text
GitHubActionsS3ValidatorRole
```

The role is read-only and scoped to the Terraform-managed S3 lab bucket.

The workflow can be started manually from GitHub Actions or through the GitHub CLI:

```bash
gh workflow run "AWS S3 Security Validation" --ref main
```

Watch the workflow run:

```bash
gh run watch
```

The workflow validates the live AWS bucket and uploads the generated report as an artifact:

```text
s3-security-report
```

This allows cloud security validation from GitHub Actions without storing AWS access keys in GitHub Secrets.

---

## Security Notes

This project follows core cloud security principles:

* No root-account access for daily operations
* MFA enabled for administrative access
* Dedicated IAM roles and identities for separate responsibilities
* Least-privilege IAM policy for the local security validator
* Separate Terraform deployer identity for infrastructure deployment
* Dedicated read-only GitHub Actions OIDC role for cloud validation
* GitHub Actions uses short-lived AWS credentials through OIDC
* AWS credentials are resolved through the AWS default credential provider chain
* The validator targets configured buckets directly and does not require account-wide S3 bucket listing
* Terraform-managed S3 lab bucket is created with Object Lock enabled
* Object Lock uses Governance mode with a 1-day default retention period for lab safety
* Bucket policy denies insecure non-TLS transport
* Bucket ownership is enforced with ACLs disabled
* Environment variables are excluded from GitHub
* Terraform state files are excluded from GitHub
* Local Terraform variable files are excluded from GitHub
* Public S3 access is blocked by default

---

## Future Roadmap

* Veeam API integration
* AI-based anomaly detection
* Local LLM integration with Ollama
* CrewAI multi-agent orchestration
* Incident response automation
* AWS SSO or temporary credentials for local development
* SSE-KMS with customer-managed keys and key rotation
* Separate OIDC-based Terraform deployment workflow with environment approval

---

## Author

Thomas Tomson
