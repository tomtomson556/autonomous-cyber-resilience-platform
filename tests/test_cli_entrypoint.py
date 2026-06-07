import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "src" / "tools" / "aws_s3_security.py"


def test_direct_validator_help_entrypoint_runs_without_pythonpath_or_aws():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("AWS_DEFAULT_REGION", None)
    environment.pop("BUCKET_NAME", None)

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), "--help"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Validate security controls for an AWS S3 backup bucket." in result.stdout
