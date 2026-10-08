import subprocess
import sysconfig
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.architecture
def test_import_linter_contracts_are_kept():
    # Resolve from the active environment so the test works with or without `uv run`.
    executable = Path(sysconfig.get_path("scripts")) / "lint-imports"
    assert executable.exists(), "import-linter must be installed"

    result = subprocess.run(
        [str(executable), "--config", str(REPO_ROOT / ".importlinter")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
