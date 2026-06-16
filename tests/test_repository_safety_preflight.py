from pathlib import Path

import pytest

from src.tools import repository_safety_preflight as preflight


VALID_AGENT = """---
name: PR Gatekeeper
description: Final PR safety reviewer for autonomous-cyber-resilience-platform.
argument-hint: "branch name, PR number, diff summary, check results, or review task"
tools: ['search/codebase', 'search/usages']
disable-model-invocation: true
---

# PR Gatekeeper

Do not make code, documentation, Git, Terraform, AWS, Azure, Veeam, workflow, or repository changes. Provide review findings and recommendations only.
"""


def write_valid_agent(root: Path, filename: str = "pr-gatekeeper.agent.md") -> Path:
    agents_dir = root / ".github" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agents_dir / filename
    agent_file.write_text(VALID_AGENT, encoding="utf-8")
    return agent_file


def finding_paths(findings):
    return {finding.path for finding in findings}


def finding_reasons(findings):
    return "\n".join(finding.reason for finding in findings)


def test_default_clean_repository_like_tree_passes(tmp_path):
    write_valid_agent(tmp_path)

    assert preflight.run_default_preflight(tmp_path) == []


def test_default_ignored_local_venv_does_not_fail(tmp_path):
    write_valid_agent(tmp_path)
    (tmp_path / ".venv").mkdir()

    assert preflight.run_default_preflight(tmp_path) == []


def test_default_ignored_local_terraform_does_not_fail(tmp_path):
    write_valid_agent(tmp_path)
    (tmp_path / "infrastructure" / "terraform" / ".terraform").mkdir(parents=True)

    assert preflight.run_default_preflight(tmp_path) == []


def test_default_allows_github_agents_and_instructions(tmp_path):
    write_valid_agent(tmp_path)
    instructions_dir = tmp_path / ".github" / "instructions"
    instructions_dir.mkdir()
    (instructions_dir / "Repository Safety Rules.instructions.md").write_text(
        "---\napplyTo: \"**\"\n---\n# Rules\n",
        encoding="utf-8",
    )

    assert preflight.run_default_preflight(tmp_path) == []


def test_default_detects_forbidden_tracked_paths(tmp_path, monkeypatch):
    write_valid_agent(tmp_path)
    monkeypatch.setattr(
        preflight,
        "_tracked_paths",
        lambda root: [
            "infrastructure/terraform/terraform.tfstate",
            "reports/s3_security_report.json",
            "backup.zip",
        ],
    )

    findings = preflight.run_default_preflight(tmp_path)

    assert "infrastructure/terraform/terraform.tfstate" in finding_paths(findings)
    assert "reports/s3_security_report.json" in finding_paths(findings)
    assert "backup.zip" in finding_paths(findings)


def test_default_detects_tracked_file_under_terraform_directory(tmp_path, monkeypatch):
    write_valid_agent(tmp_path)
    tracked_path = "infrastructure/terraform/.terraform/providers/example.txt"
    monkeypatch.setattr(preflight, "_tracked_paths", lambda root: [tracked_path])

    findings = preflight.run_default_preflight(tmp_path)

    assert tracked_path in finding_paths(findings)
    assert ".terraform paths" in finding_reasons(findings)


def test_valid_renamed_agent_files_pass_metadata_validation(tmp_path):
    for filename in (
        "pr-gatekeeper.agent.md",
        "python-contract-validator.agent.md",
        "terraform-state-guardian.agent.md",
        "veeam-api-safety-reviewer.agent.md",
    ):
        write_valid_agent(tmp_path, filename)

    assert preflight.validate_agent_files(tmp_path) == []


def test_agent_file_with_spaces_in_filename_is_rejected(tmp_path):
    write_valid_agent(tmp_path, "PR Gatekeeper.agent.md")

    findings = preflight.validate_agent_files(tmp_path)

    assert ".github/agents/PR Gatekeeper.agent.md" in finding_paths(findings)
    assert "must not contain spaces" in finding_reasons(findings)


def test_agent_file_without_required_frontmatter_is_rejected(tmp_path):
    agent_file = write_valid_agent(tmp_path)
    agent_file.write_text("# PR Gatekeeper\n", encoding="utf-8")

    findings = preflight.validate_agent_files(tmp_path)

    assert "missing YAML frontmatter" in finding_reasons(findings)


def test_agent_file_with_write_style_tool_is_rejected(tmp_path):
    agent_file = write_valid_agent(tmp_path)
    agent_file.write_text(
        VALID_AGENT.replace(
            "tools: ['search/codebase', 'search/usages']",
            "tools: ['search/codebase', 'repo/write']",
        ),
        encoding="utf-8",
    )

    findings = preflight.validate_agent_files(tmp_path)

    assert "tools must exactly match" in finding_reasons(findings)


def test_agent_missing_reviewer_only_wording_is_rejected(tmp_path):
    agent_file = write_valid_agent(tmp_path)
    agent_file.write_text(
        VALID_AGENT.replace(" Provide review findings and recommendations only.", ""),
        encoding="utf-8",
    )

    findings = preflight.validate_agent_files(tmp_path)

    assert "missing required reviewer-only language" in finding_reasons(findings)


def test_agent_missing_no_change_wording_is_rejected(tmp_path):
    agent_file = write_valid_agent(tmp_path)
    agent_file.write_text(
        VALID_AGENT.replace(
            "Do not make code, documentation, Git, Terraform, AWS, Azure, Veeam, workflow, or repository changes. ",
            "",
        ),
        encoding="utf-8",
    )

    findings = preflight.validate_agent_files(tmp_path)

    assert "missing required no-change language" in finding_reasons(findings)


def test_agent_disable_model_invocation_policy_is_enforced(tmp_path):
    agent_file = write_valid_agent(tmp_path)
    agent_file.write_text(
        VALID_AGENT.replace("disable-model-invocation: true", ""),
        encoding="utf-8",
    )

    findings = preflight.validate_agent_files(tmp_path)

    assert "disable-model-invocation must be present and true" in finding_reasons(
        findings
    )


@pytest.mark.parametrize(
    ("relative_path", "expected_reason"),
    [
        (".terraform", ".terraform paths"),
        (
            "infrastructure/terraform/.terraform/providers/example.txt",
            ".terraform paths",
        ),
        ("bin/terraform-provider-aws_v5", "Terraform provider binaries"),
        ("terraform.tfstate", "Terraform state files"),
        ("terraform.tfstate.backup", "Terraform state files"),
        ("prod.tfvars", "Real Terraform variable files"),
        (".env", ".env files"),
        ("nested/archive.zip", "ZIP archives"),
        (".agents", ".agents directories"),
        (".codex", ".codex directories"),
        (".venv", ".venv directories"),
        (".pytest_cache", ".pytest_cache directories"),
        (".ruff_cache", ".ruff_cache directories"),
        ("src/__pycache__", "__pycache__ directories"),
        ("reports/s3_security_report.json", "Generated runtime reports"),
    ],
)
def test_backup_scan_detects_forbidden_artifacts(
    tmp_path,
    relative_path,
    expected_reason,
):
    path = tmp_path / relative_path
    if "." not in path.name or path.name in {
        ".terraform",
        ".agents",
        ".codex",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }:
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("do not read", encoding="utf-8")

    findings = preflight.run_backup_scan(tmp_path)

    assert relative_path in finding_paths(findings)
    assert expected_reason in finding_reasons(findings)


def test_backup_scan_allows_tfvars_examples_by_filename(tmp_path):
    for filename in (
        "terraform.tfvars.example",
        "prod.tfvars.sample",
        "dev.tfvars.template",
        "test.tfvars.dist",
    ):
        (tmp_path / filename).write_text("example only", encoding="utf-8")

    assert preflight.run_backup_scan(tmp_path) == []


def test_backup_scan_detects_git_file(tmp_path):
    (tmp_path / ".git").write_text("gitdir: ../real-git-dir", encoding="utf-8")

    findings = preflight.run_backup_scan(tmp_path)

    assert ".git" in finding_paths(findings)
    assert ".git paths" in finding_reasons(findings)


def test_backup_manifest_detects_forbidden_paths_without_files(tmp_path):
    manifest = tmp_path / "backup-manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                "# generated path list",
                ".git/",
                "infrastructure/terraform/terraform.tfstate",
                "infrastructure/terraform/.terraform/providers/example.txt",
                "reports/s3_security_report.json",
                "terraform.tfvars.example",
            ]
        ),
        encoding="utf-8",
    )

    findings = preflight.run_backup_manifest(tmp_path, manifest)

    assert ".git" in finding_paths(findings)
    assert "infrastructure/terraform/terraform.tfstate" in finding_paths(findings)
    assert (
        "infrastructure/terraform/.terraform/providers/example.txt"
        in finding_paths(findings)
    )
    assert "reports/s3_security_report.json" in finding_paths(findings)
    assert "terraform.tfvars.example" not in finding_paths(findings)


def test_backup_scan_does_not_read_sensitive_file_contents(tmp_path, monkeypatch):
    for filename in (
        "terraform.tfstate",
        "prod.tfvars",
        ".env",
        "archive.zip",
    ):
        (tmp_path / filename).write_text("sensitive", encoding="utf-8")
    (tmp_path / ".terraform").mkdir()
    (tmp_path / ".terraform" / "provider.txt").write_text("provider", encoding="utf-8")

    def fail_read_text(self, *args, **kwargs):
        raise AssertionError(f"read_text must not be called for {self}")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    findings = preflight.run_backup_scan(tmp_path)

    expected_paths = {
        ".env",
        ".terraform",
        ".terraform/provider.txt",
        "archive.zip",
        "prod.tfvars",
        "terraform.tfstate",
    }
    assert expected_paths <= finding_paths(findings)
