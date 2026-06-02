# Autonomous Cyber-Resilience Platform

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

The platform validates whether backup storage is configured according to modern cloud security best practices.

---

## Current Features

### S3 Security Validation

Automated validation of:

* Bucket Versioning
* Server-side Encryption
* Object Lock capability
* Public Access Block configuration

### AWS Integration

* IAM-based authentication
* AWS CLI integration
* boto3 SDK automation

### Security Controls

* Immutable-storage-ready configuration
* Encrypted object storage
* Public exposure prevention

### Infrastructure as Code with Terraform

The project includes Terraform-based infrastructure deployment for the S3 lab environment.

Terraform provisions:

- S3 bucket
- Bucket versioning
- Server-side encryption
- Public access blocking
- Resource tagging
- Terraform outputs for bucket name, ARN, and region

This demonstrates reproducible infrastructure deployment and cloud security automation using Infrastructure as Code.

---

## Technologies

* Python 3
* AWS S3
* boto3
* Git
* GitHub
* AWS CLI
* Terraform
* Infrastructure as Code

---

## Example Validation Output

```text
S3 Security Validation Report
============================
Versioning: PASS
Encryption: PASS
Object Lock: PASS
Public Access Block: PASS

Overall Status: SECURE
```

---


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

### Validate configuration

```bash
terraform validate
```

### Preview infrastructure changes

```bash
terraform plan
```

### Deploy infrastructure

```bash
terraform apply
```

### Show outputs

```bash
terraform output
```

Example outputs:

```text
bucket_name   = "cyber-resilience-terraform-lab-tom-2026"
bucket_arn    = "arn:aws:s3:::cyber-resilience-terraform-lab-tom-2026"
bucket_region = "eu-central-1"
```

State files are intentionally excluded from GitHub via `.gitignore`.

---

## Future Roadmap

* Veeam API integration
* AI-based anomaly detection
* Local LLM integration with Ollama
* CrewAI multi-agent orchestration
* Terraform infrastructure deployment
* Incident response automation

---

## Author

Thomas Tomson
