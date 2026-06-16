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

## Repository safety preflight

GitHub workspace agent files under `.github/agents/` use no-space,
lowercase kebab-case filenames ending in `.agent.md`, for example
`pr-gatekeeper.agent.md`. Human-readable agent names remain inside each file.
The no-space filename convention applies to `.github/agents/*.agent.md`; this
does not rename `.github/instructions/Repository Safety Rules.instructions.md`.

Run the local repository safety preflight when changing repository safety
configuration:

```bash
.venv/bin/python -m src.tools.repository_safety_preflight --mode default
```

Default mode validates tracked/versioned repository files and safe metadata,
including `.github/agents/*.agent.md`. It is safe for normal local development
and must not fail merely because ignored local artifacts such as `.venv/`,
`.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.terraform/`, provider
binaries, or local Terraform state exist in the workspace.

Backup-scan mode is for supplied backup, ZIP-staging, or manifest paths:

```bash
.venv/bin/python -m src.tools.repository_safety_preflight --mode backup-scan --path <path>
.venv/bin/python -m src.tools.repository_safety_preflight --mode backup-scan --path <root> --manifest <manifest>
```

Backup-scan mode checks path names for artifacts that must not enter backups or
ZIPs. A manifest is a newline-delimited list of paths to check. It does not
inspect ZIP contents. The preflight checks paths and safe
metadata only; it must not read Terraform state, real `.tfvars`, `.env`,
provider binary, ZIP, or `.terraform/` file contents. It does not delete,
clean, mutate, run Terraform, call AWS or Azure, call Veeam, replace human
review, or prove GitHub Copilot runtime enforcement.

`disable-model-invocation` in agent frontmatter is treated only as an
invocation or manual-selection control for the repository's intended policy. It
is not a no-model or no-LLM guarantee. `argument-hint` is advisory and must not
be treated as an enforced GitHub.com security control.

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
