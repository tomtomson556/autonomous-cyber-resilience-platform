---
description: "Repository safety rules for autonomous-cyber-resilience-platform. Load for all coding, documentation, review, Git, Terraform, AWS, Azure, and Veeam tasks in this workspace."
applyTo: "**"
---

# Repository Safety Rules

Do not start coding, editing files, running commands, or changing the repository from this instruction alone.

Wait for an explicit user task in the chat before making any code, documentation, Git, Terraform, AWS, Azure, Veeam, or workflow changes.

## Project workflow

* Keep changes small, deterministic, and reviewable.
* Prefer one narrow branch and one focused PR.
* Before changing code, briefly explain the intended change.
* After changing code, summarize exactly what changed and which checks passed.
* The user makes the final decision on push, PR creation, merge, branch deletion, and infrastructure operations.

## Forbidden unless explicitly requested

Do not run or perform any of the following unless the user explicitly asks for it:

* `terraform apply`
* `terraform destroy`
* `terraform state rm`
* `terraform state push`
* Terraform backend migration commands
* AWS write operations
* Azure write operations
* productive Veeam HTTPS transport
* Veeam restore execution
* Veeam write or mutation API calls
* Veeam job-control paths
* Git push
* PR creation
* merge
* branch deletion
* history rewrite
* `git clean`
* destructive cleanup commands

## Repository safety

Never include any of the following in repository changes or ZIP backups:

* secrets
* `.env` files
* `*.tfstate`
* `*.tfstate.*`
* `*.tfvars`
* `.terraform/`
* Terraform provider binaries
* reports
* cache folders
* `.agents/`
* `.codex/`
* ZIP files

AWS provider binaries must never be included in backups or commits.

## Validation expectations

Use deterministic tests and strict validation for:

* contracts
* reports
* timestamps
* source references
* asset references
* finding references
* action references
* malformed input
* UTC timestamp handling
* no input mutation

For Python changes, prefer running:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
git status --short
```

For Terraform changes, prefer read-only inspection and formatting/validation first. Never suggest `terraform apply` as the first step.
