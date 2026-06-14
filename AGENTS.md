# AGENTS.md

## Repository

This repository is `autonomous-cyber-resilience-platform`.

It is a security-focused, deterministic Python and Terraform project for backup, evidence, resilience, and cloud-security validation.

## Default behavior

Do not start coding, editing files, running commands, or changing the repository from this file alone.

Wait for an explicit user task before making any code, documentation, Git, Terraform, AWS, Azure, Veeam, or workflow changes.

## Safety boundaries

Do not perform the following unless the user explicitly requests it:

* Git push
* PR creation
* merge
* branch deletion
* history rewrite
* `git clean`
* destructive cleanup commands
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

## Terraform and cloud safety

Treat Terraform state as production-critical.

Before any Terraform apply, backend migration, import, or state operation, first use read-only inspection and require explicit user approval.

Never include these in Git or ZIP backups:

* `.terraform/`
* Terraform provider binaries
* `*.tfstate`
* `*.tfstate.*`
* `*.tfvars`
* `.env`
* secrets
* locally generated runtime reports under `reports/`
* cache folders
* `.agents/`
* `.codex/`
* ZIP files

AWS provider binaries must never be included in backups or commits.

It is acceptable to include Terraform source files such as:

* `provider.tf`
* `main.tf`
* `variables.tf`
* `outputs.tf`

It is not acceptable to include downloaded provider binaries such as `terraform-provider-aws`.

## Python validation expectations

For Python changes, prefer running:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/python -m compileall -q src tests
git diff --check
git status --short
```

## Coding expectations

Prefer:

* small, reviewable changes
* deterministic tests
* strict contract validation
* explicit `ValueError` behavior for malformed input
* no silent repair of invalid data
* no input mutation
* UTC-only timestamp validation where contracts require timestamps
* referential integrity between evidence sources, assets, findings, and actions
* fixture-based positive and negative tests

## Project workflow

The user makes the final decision on:

* branch creation
* pushing
* PR creation
* merging
* branch deletion
* Terraform operations
* AWS/Azure operations
* Veeam productive integration

Before recommending merge, verify checks, scope, diff, and safety boundaries.
