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
* locally generated runtime reports under `reports/`
* cache folders
* `.agents/`
* `.codex/`
* ZIP files

AWS provider binaries must never be included in backups or commits.

## Local safety preflight

GitHub workspace agent files under `.github/agents/` must use no-space,
lowercase kebab-case filenames ending in `.agent.md`, for example
`pr-gatekeeper.agent.md`. Keep human-readable agent names inside the files.
This convention is intentionally limited to `.github/agents/*.agent.md`; this
instruction file keeps its existing filename.

Use the local repository safety preflight for deterministic safety checks:

```bash
.venv/bin/python -m src.tools.repository_safety_preflight --mode default
```

Default mode validates tracked/versioned repository files and safe metadata,
including `.github/agents/*.agent.md`. It is suitable for normal local
development and must not fail only because ignored local artifacts such as
`.venv/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.terraform/`,
provider binaries, or local Terraform state exist in the workspace.

Use backup-scan mode only for supplied backup, ZIP-staging, or manifest paths:

```bash
.venv/bin/python -m src.tools.repository_safety_preflight --mode backup-scan --path <path>
.venv/bin/python -m src.tools.repository_safety_preflight --mode backup-scan --path <root> --manifest <manifest>
```

Backup-scan mode checks path names for backup and ZIP blockers. It does not
inspect ZIP contents. A manifest is a newline-delimited list of paths to check.
The preflight checks paths and safe metadata only; it
must not read Terraform state, real `.tfvars`, `.env`, provider binary, ZIP, or
`.terraform/` file contents. It does not delete or clean anything, mutate the
repository, run Terraform, call AWS or Azure, call Veeam, or replace human
review.

Agent metadata validation enforces this repository's intended local policy. It
does not prove GitHub.com schema support or Copilot runtime enforcement.
`disable-model-invocation` is an invocation or manual-selection control, not a
no-model or no-LLM guarantee. `argument-hint` is advisory and must not be
treated as an enforced GitHub.com security control.

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
