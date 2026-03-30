"""Integration tests: run the built binary against fixture files."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_XML = FIXTURES / "VolvoEWR150E.xml"
REAL_I3D = FIXTURES / "VolvoEWR150E.i3d"

# Resolve the installed console-script entry-point for the current venv.
# Works both with `uv run pytest` and a plain venv.
_SCRIPT = Path(sys.executable).parent / "fs25-mod-checker"
_SCRIPT_EXE = _SCRIPT.with_suffix(".exe")
if _SCRIPT_EXE.exists():
    ENTRY_POINT = [str(_SCRIPT_EXE)]
elif _SCRIPT.exists():
    ENTRY_POINT = [str(_SCRIPT)]
else:
    ENTRY_POINT = [sys.executable, "-m", "fs25_mod_checker"]


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ENTRY_POINT + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _project_version() -> str:
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pyproject_data = tomllib.loads(pyproject_text)
    return pyproject_data["project"]["version"]


@pytest.fixture
def require_fixtures():
    if not REAL_XML.exists() or not REAL_I3D.exists():
        pytest.skip("Fixture files not present")


# ---------------------------------------------------------------------------
# Version flag (does not need fixture files)
# ---------------------------------------------------------------------------

class TestVersionFlag:
    def test_version_flag_prints_project_version(self):
        result = _run("--version")
        assert result.returncode == 0
        assert result.stdout.strip() == f"fs25-mod-checker {_project_version()}"

    def test_version_flag_does_not_require_fixture_files(self):
        result = _run("--version", cwd=PROJECT_ROOT)
        assert result.returncode == 0
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestCLIHappyPath:
    @pytest.fixture(autouse=True)
    def _require_fixtures(self, require_fixtures):  # noqa: PT004
        pass

    def test_exit_code_1_when_problems_found(self):
        result = _run(str(REAL_XML))
        # The real file has known problems, so exit code must be 1
        assert result.returncode == 1

    def test_stdout_contains_problem_in_matcher_format(self):
        result = _run(str(REAL_XML))
        # Format: path:line:column: warning: rule_id: message
        assert ":" in result.stdout
        assert "warning:" in result.stdout

    def test_stdout_contains_rule_id(self):
        result = _run(str(REAL_XML))
        assert "unused-mapping-id" in result.stdout

    def test_stdout_shows_loading_progress(self):
        result = _run(str(REAL_XML))
        assert "Loading and parsing files" in result.stdout

    def test_explicit_i3d_flag(self):
        result = _run(
            str(REAL_XML),
            "--i3d", str(REAL_I3D),
        )
        assert result.returncode in (0, 1)  # either is valid


# ---------------------------------------------------------------------------
# Clean file (no problems expected)
# ---------------------------------------------------------------------------

class TestCLICleanFile:
    def test_exit_code_0_when_no_problems(self, tmp_path: Path):
        # Build a minimal valid pair with one mapping that IS referenced
        i3d = tmp_path / "clean.i3d"
        i3d.write_text("""\
<?xml version="1.0" encoding="utf-8"?>
<i3D>
  <Scene>
    <Shape name="myNode"/>
  </Scene>
</i3D>
""", encoding="utf-8")
        xml = tmp_path / "clean.xml"
        xml.write_text("""\
<?xml version="1.0" encoding="utf-8"?>
<vehicle>
  <i3dMappings>
    <i3dMapping id="myNode" node="0"/>
  </i3dMappings>
  <component node="myNode"/>
</vehicle>
""", encoding="utf-8")
        result = _run(str(xml), "--i3d", str(i3d))
        assert result.returncode == 0
        assert "No problems found" in result.stdout


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestCLIErrorHandling:
    def test_missing_xml_exits_nonzero(self, tmp_path: Path):
        result = _run(str(tmp_path / "does_not_exist.xml"))
        assert result.returncode != 0

    def test_missing_xml_prints_error(self, tmp_path: Path):
        result = _run(str(tmp_path / "does_not_exist.xml"))
        assert "error" in result.stderr.lower() or "not found" in result.stderr.lower()

    def test_missing_i3d_exits_nonzero(self, tmp_path: Path):
        xml = tmp_path / "test.xml"
        xml.write_text("<root/>", encoding="utf-8")
        result = _run(str(xml), "--i3d", str(tmp_path / "missing.i3d"))
        assert result.returncode != 0

    def test_no_args_shows_usage(self):
        result = _run()
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower()


# ---------------------------------------------------------------------------
# Workspace initialization
# ---------------------------------------------------------------------------

class TestWorkspaceInit:
    def test_init_creates_vscode_dir(self, tmp_path: Path):
        result = _run("--init", cwd=tmp_path)
        assert result.returncode == 0
        assert (tmp_path / ".vscode").exists()
        assert (tmp_path / ".vscode").is_dir()

    def test_init_creates_tasks_json(self, tmp_path: Path):
        result = _run("--init", cwd=tmp_path)
        assert result.returncode == 0
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        assert tasks_file.exists()

    def test_tasks_json_is_valid(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        assert tasks_data["version"] == "2.0.0"
        assert "tasks" in tasks_data
        assert isinstance(tasks_data["tasks"], list)

    def test_init_creates_check_task(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        labels = [t.get("label") for t in tasks_data["tasks"]]
        assert "Check Mod (fs25-mod-checker)" in labels

    def test_init_creates_package_task(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        labels = [t.get("label") for t in tasks_data["tasks"]]
        assert "Package Mod (Create ZIP)" in labels

    def test_package_task_uses_checker_not_powershell(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        package_task = next(
            t for t in tasks_data["tasks"]
            if t.get("label") == "Package Mod (Create ZIP)"
        )
        assert package_task.get("command", "").lower() != "powershell"
        assert "--package" in (package_task.get("args") or [])

    def test_check_task_has_problem_matcher(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        tasks_file = tmp_path / ".vscode" / "tasks.json"
        tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        check_task = next(
            t for t in tasks_data["tasks"]
            if t.get("label") == "Check Mod (fs25-mod-checker)"
        )
        assert "problemMatcher" in check_task
        assert len(check_task["problemMatcher"]) > 0
        matcher = check_task["problemMatcher"][0]
        assert matcher.get("name") == "fs25-mod-checker"
        assert "pattern" in matcher

    def test_init_idempotent(self, tmp_path: Path):
        _run("--init", cwd=tmp_path)
        first_content = (tmp_path / ".vscode" / "tasks.json").read_text()
        _run("--init", cwd=tmp_path)
        second_content = (tmp_path / ".vscode" / "tasks.json").read_text()
        # Both should have the same number of tasks (should not duplicate)
        first_data = json.loads(first_content)
        second_data = json.loads(second_content)
        assert len(first_data["tasks"]) == len(second_data["tasks"])

    def test_init_stdout_shows_next_steps(self, tmp_path: Path):
        result = _run("--init", cwd=tmp_path)
        assert result.returncode == 0
        output = result.stdout
        assert "Initialized" in output or "[OK]" in output
        assert "tasks.json" in output
