# Security Policy

## Supported Versions

This project is a proof-of-concept lab environment. Security updates and improvements are applied to the latest version on the `main` branch.

| Version | Supported |
|---|---|
| main | Yes |

## Reporting a Vulnerability

If you discover a potential security issue in this project, please do not open a public GitHub issue containing sensitive details.

Instead, report the issue privately through GitHub Security Advisories if available.

Please include:

- A clear description of the issue
- Steps to reproduce
- Potential impact
- Suggested remediation, if known

## Security Design Principles

This project follows the following security principles:

- No root-account usage for daily operations
- MFA for administrative access
- Least-privilege IAM policies
- Separate identities for validation and deployment
- No secrets committed to GitHub
- Terraform state excluded from version control
- Public S3 access blocked by default
- Machine-readable security validation reports

## Out of Scope

The following are out of scope for this proof-of-concept:

- Production workload protection
- Real customer data
- Public exploitation testing
- Unauthorized access to AWS resources
- Denial-of-service testing

## Disclaimer

This project is intended for educational and portfolio purposes. It should not be used as-is for production environments without additional hardening, monitoring, logging, and security review.
