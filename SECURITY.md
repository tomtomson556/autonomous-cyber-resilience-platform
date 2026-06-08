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

## AI and Automation Security

AI components are advisory, not authoritative. They may analyze evidence,
prioritize findings, summarize results, and prepare reports or proposals. They
must not independently modify backup jobs, restore points, retention policies,
IAM, Veeam or AWS configurations, or restore operations.

The enterprise-controlled AI advisory and prioritization layer that influences
operational prioritization or action proposals must run locally or in an
environment technically, organizationally, and contractually controlled by the
enterprise.
External AI services may support only non-critical tasks such as summarization,
wording, documentation, and drafting.

Rule-based validators remain authoritative for `PASS`, `FAIL`, and `UNKNOWN`.
`UNKNOWN` represents missing or incomplete evidence and must not be communicated
as a confirmed vulnerability.

Critical actions remain approval-controlled and require deterministic policy
checks, versioned runbooks or Infrastructure as Code, least-privilege execution
identities, audit logging, and explicit human approval. AI prompts, outputs,
recommendations, and resulting decision proposals should be recorded in an
audit-ready manner.

## Out of Scope

The following are out of scope for this proof-of-concept:

- Production workload protection
- Autonomous production changes or recovery execution
- Real customer data
- Public exploitation testing
- Unauthorized access to AWS resources
- Denial-of-service testing

## Disclaimer

This project is intended for educational and portfolio purposes. It should not be used as-is for production environments without additional hardening, monitoring, logging, and security review.
