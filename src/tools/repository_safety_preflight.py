import argparse
import ast
import fnmatch
import json
import re
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path


AGENT_TOOLS_ALLOWLIST = ("search/codebase", "search/usages")
AGENT_REQUIRED_FIELDS = frozenset(
    {
        "name",
        "description",
        "argument-hint",
        "tools",
        "disable-model-invocation",
    }
)
AGENT_FILENAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.agent\.md$")
REVIEWER_ONLY_TEXT = "Provide review findings and recommendations only"
NO_CHANGE_TEXT = (
    "Do not make code, documentation, Git, Terraform, AWS, Azure, Veeam, "
    "workflow, or repository changes"
)
FORBIDDEN_AGENT_PHRASES = (
    "you may implement",
    "apply changes",
    "run terraform apply",
    "perform aws write operations",
    "merge the pr",
    "push the branch",
    "delete the branch",
)
NEGATED_AGENT_PREFIXES = (
    "do not ",
    "don't ",
    "never ",
    "must not ",
    "no ",
    "without ",
)


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    reason: str


def run_default_preflight(root_path: Path) -> list[Finding]:
    root = root_path.resolve()
    findings = []
    findings.extend(_scan_tracked_paths(root))
    findings.extend(_scan_versioned_safety_paths(root))
    findings.extend(validate_agent_files(root))
    return sorted(set(findings))


def run_backup_scan(root_path: Path) -> list[Finding]:
    root = root_path.resolve()
    findings = []
    for path in _iter_backup_paths(root):
        relative_path = _relative_path(root, path)
        reason = _backup_artifact_reason(relative_path, path.is_dir())
        if reason is not None:
            findings.append(Finding(relative_path, reason))
    return sorted(set(findings))


def run_backup_manifest(root_path: Path, manifest_path: Path) -> list[Finding]:
    root = root_path.resolve()
    manifest = manifest_path.resolve()
    manifest_name = manifest.name
    if (
        _is_tfstate_name(manifest_name)
        or _is_real_tfvars_name(manifest_name)
        or _is_zip_name(manifest_name)
        or _is_provider_binary_name(manifest_name)
        or manifest_name == ".env"
        or ".terraform" in manifest.parts
    ):
        return [
            Finding(
                _relative_path(root, manifest),
                "Backup manifest path is classified as sensitive and was not read.",
            )
        ]

    findings = []
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        manifest_entry = raw_line.strip()
        if not manifest_entry or manifest_entry.startswith("#"):
            continue
        normalized_entry = manifest_entry.rstrip("/")
        reason = _backup_artifact_reason(
            normalized_entry,
            _manifest_entry_is_directory(manifest_entry),
        )
        if reason is not None:
            findings.append(Finding(normalized_entry, reason))
    return sorted(set(findings))


def validate_agent_files(root_path: Path) -> list[Finding]:
    root = root_path.resolve()
    agents_dir = root / ".github" / "agents"
    findings = []
    if not agents_dir.exists():
        return [Finding(".github/agents", "Missing versioned GitHub agents directory.")]
    if not agents_dir.is_dir():
        return [Finding(".github/agents", "GitHub agents path must be a directory.")]

    agent_files = sorted(agents_dir.glob("*.agent.md"))
    if not agent_files:
        return [Finding(".github/agents", "No GitHub agent files found.")]

    for agent_file in agent_files:
        relative_path = _relative_path(root, agent_file)
        findings.extend(_validate_agent_filename(agent_file.name, relative_path))
        text = agent_file.read_text(encoding="utf-8")
        try:
            frontmatter, body = _parse_frontmatter(text)
        except ValueError as error:
            findings.append(Finding(relative_path, str(error)))
            continue
        findings.extend(_validate_agent_frontmatter(relative_path, frontmatter))
        findings.extend(_validate_agent_body(relative_path, body))

    for path in sorted(agents_dir.iterdir()):
        if path.is_file() and not path.name.endswith(".agent.md"):
            findings.append(
                Finding(
                    _relative_path(root, path),
                    "GitHub agent files must end with .agent.md.",
                )
            )

    return findings


def _scan_tracked_paths(root: Path) -> list[Finding]:
    findings = []
    for path_text in _tracked_paths(root):
        path = Path(path_text)
        reason = _versioned_artifact_reason(path.as_posix(), is_dir=False)
        if reason is not None:
            findings.append(Finding(path.as_posix(), reason))
    return findings


def _scan_versioned_safety_paths(root: Path) -> list[Finding]:
    findings = []
    for relative_path in (
        ".github",
        "AGENTS.md",
        ".gitignore",
    ):
        path = root / relative_path
        if not path.exists():
            continue
        paths = _iter_paths(path)
        for candidate in paths:
            candidate_relative = _relative_path(root, candidate)
            reason = _versioned_artifact_reason(
                candidate_relative,
                candidate.is_dir(),
            )
            if reason is not None:
                findings.append(Finding(candidate_relative, reason))
    return findings


def _tracked_paths(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
            text=False,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    output = result.stdout.decode("utf-8")
    return [path for path in output.split("\0") if path]


def _iter_backup_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*"), key=lambda path: path.as_posix())


def _iter_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*"), key=lambda item: item.as_posix())


def _manifest_entry_is_directory(manifest_entry: str) -> bool:
    path = Path(manifest_entry.rstrip("/"))
    name = path.name
    return manifest_entry.endswith("/") or name in {
        ".git",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        ".terraform",
        ".agents",
        ".codex",
    }


def _versioned_artifact_reason(relative_path: str, is_dir: bool) -> str | None:
    parts = Path(relative_path).parts
    name = parts[-1] if parts else relative_path
    if _is_sensitive_tfvars_example(name):
        return None
    if ".terraform" in parts:
        return ".terraform paths must not be versioned or safety-controlled."
    if is_dir and name == "reports":
        return None
    if any(part == "reports" for part in parts) and not is_dir:
        return "Generated runtime reports must not be tracked."
    if name == ".env":
        return ".env files must not be tracked."
    if _is_tfstate_name(name):
        return "Terraform state files must not be tracked."
    if _is_real_tfvars_name(name):
        return "Real Terraform variable files must not be tracked."
    if _is_zip_name(name):
        return "ZIP archives must not be tracked or kept in versioned safety paths."
    if _is_provider_binary_name(name):
        return "Terraform provider binaries must not be tracked."
    return None


def _backup_artifact_reason(relative_path: str, is_dir: bool) -> str | None:
    parts = Path(relative_path).parts
    name = parts[-1] if parts else relative_path
    if _is_sensitive_tfvars_example(name):
        return None
    if name == ".git":
        return ".git paths must not be included in backups."
    if ".terraform" in parts:
        return ".terraform paths must not be included in backups."
    if is_dir and name in {".git", ".venv", ".pytest_cache", ".ruff_cache"}:
        return f"{name} directories must not be included in backups."
    if is_dir and name == "__pycache__":
        return "__pycache__ directories must not be included in backups."
    if is_dir and name in {".agents", ".codex"}:
        return f"{name} directories must not be included in backups."
    if any(part == "reports" for part in parts) and not is_dir:
        return "Generated runtime reports must not be included in backups."
    if name == ".env":
        return ".env files must not be included in backups."
    if _is_tfstate_name(name):
        return "Terraform state files must not be included in backups."
    if _is_real_tfvars_name(name):
        return "Real Terraform variable files must not be included in backups."
    if _is_zip_name(name):
        return "ZIP archives must not be included in backups."
    if _is_provider_binary_name(name):
        return "Terraform provider binaries must not be included in backups."
    return None


def _validate_agent_filename(filename: str, relative_path: str) -> list[Finding]:
    findings = []
    if " " in filename:
        findings.append(Finding(relative_path, "Agent filename must not contain spaces."))
    if AGENT_FILENAME_PATTERN.fullmatch(filename) is None:
        findings.append(
            Finding(
                relative_path,
                "Agent filename must be lowercase kebab-case and end with .agent.md.",
            )
        )
    return findings


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("Agent file is missing YAML frontmatter.")
    closing_marker = text.find("\n---\n", 4)
    if closing_marker == -1:
        raise ValueError("Agent file frontmatter is not closed.")
    raw_frontmatter = text[4:closing_marker]
    body = text[closing_marker + len("\n---\n") :]
    return _parse_simple_frontmatter(raw_frontmatter), body


def _parse_simple_frontmatter(raw_frontmatter: str) -> dict:
    frontmatter = {}
    for line_number, raw_line in enumerate(raw_frontmatter.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid frontmatter line {line_number}.")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise ValueError(f"Invalid frontmatter line {line_number}.")
        frontmatter[key] = _parse_frontmatter_value(value, line_number)
    return frontmatter


def _parse_frontmatter_value(value: str, line_number: int) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("["):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"Invalid frontmatter list on line {line_number}.") from error
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise ValueError(f"Invalid frontmatter list on line {line_number}.")
        return parsed
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as error:
            raise ValueError(f"Invalid frontmatter string on line {line_number}.") from error
        if not isinstance(parsed, str):
            raise ValueError(f"Invalid frontmatter string on line {line_number}.")
        return parsed
    return value


def _validate_agent_frontmatter(
    relative_path: str,
    frontmatter: dict,
) -> list[Finding]:
    findings = []
    missing_fields = sorted(AGENT_REQUIRED_FIELDS - frontmatter.keys())
    if missing_fields:
        findings.append(
            Finding(
                relative_path,
                f"Agent frontmatter is missing required fields: {missing_fields}.",
            )
        )
    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip() or "-" in name:
        findings.append(Finding(relative_path, "Agent name must remain human-readable."))
    tools = frontmatter.get("tools")
    if list(tools) != list(AGENT_TOOLS_ALLOWLIST) if isinstance(tools, list) else True:
        findings.append(
            Finding(
                relative_path,
                "Agent tools must exactly match the repository read/search allowlist.",
            )
        )
    if frontmatter.get("disable-model-invocation") is not True:
        findings.append(
            Finding(
                relative_path,
                "Agent disable-model-invocation must be present and true.",
            )
        )
    return findings


def _validate_agent_body(relative_path: str, body: str) -> list[Finding]:
    findings = []
    if REVIEWER_ONLY_TEXT not in body:
        findings.append(
            Finding(relative_path, "Agent is missing required reviewer-only language.")
        )
    if NO_CHANGE_TEXT not in body:
        findings.append(
            Finding(relative_path, "Agent is missing required no-change language.")
        )
    lower_body = body.lower()
    for phrase in FORBIDDEN_AGENT_PHRASES:
        if _contains_unnegated_phrase(lower_body, phrase):
            findings.append(
                Finding(relative_path, f"Agent contains forbidden phrase: {phrase}.")
            )
    return findings


def _contains_unnegated_phrase(text: str, phrase: str) -> bool:
    start = 0
    while True:
        index = text.find(phrase, start)
        if index == -1:
            return False
        prefix = text[max(0, index - 20) : index]
        if not any(prefix.endswith(negation) for negation in NEGATED_AGENT_PREFIXES):
            return True
        start = index + len(phrase)


def _is_sensitive_tfvars_example(filename: str) -> bool:
    return any(
        fnmatch.fnmatchcase(
            filename,
            pattern,
        )
        for pattern in (
            "*.tfvars.example",
            "*.tfvars.sample",
            "*.tfvars.template",
            "*.tfvars.dist",
        )
    )


def _is_tfstate_name(filename: str) -> bool:
    return fnmatch.fnmatchcase(filename, "*.tfstate") or fnmatch.fnmatchcase(
        filename,
        "*.tfstate.*",
    )


def _is_real_tfvars_name(filename: str) -> bool:
    return fnmatch.fnmatchcase(filename, "*.tfvars") and not _is_sensitive_tfvars_example(
        filename
    )


def _is_zip_name(filename: str) -> bool:
    return filename.lower().endswith(".zip")


def _is_provider_binary_name(filename: str) -> bool:
    return filename.startswith("terraform-provider-aws")


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _print_findings(findings: list[Finding], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
        return
    for finding in findings:
        print(f"{finding.path}: {finding.reason}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repository safety preflight checks.",
    )
    parser.add_argument(
        "--mode",
        choices=("default", "backup-scan"),
        default="default",
        help="Preflight mode to run.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Repository root or backup path to scan.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional newline-delimited path manifest for backup-scan mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print findings as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mode == "default" and args.manifest is not None:
        print("--manifest is only valid with --mode backup-scan")
        return 1
    if args.mode == "default":
        findings = run_default_preflight(args.path)
    elif args.manifest is not None:
        findings = run_backup_manifest(args.path, args.manifest)
    else:
        findings = run_backup_scan(args.path)
    _print_findings(findings, json_output=args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
