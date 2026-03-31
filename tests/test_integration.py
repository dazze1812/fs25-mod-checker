"""Integration tests: run the built binary against fixture files."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MOD_FOLDER = FIXTURES / "FS25_VolvoEWR150E_Fippe3DModding"

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
    project_root = Path(__file__).resolve().parents[1]
    pyproject_text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    pyproject_data = tomllib.loads(pyproject_text)
    return pyproject_data["project"]["version"]


# ---------------------------------------------------------------------------
# Version flag (does not need fixture files)
# ---------------------------------------------------------------------------

class TestVersionFlag:
    def test_version_flag_prints_project_version(self):
        result = _run("--version")
        assert result.returncode == 0
        assert result.stdout.strip() == f"fs25-mod-checker {_project_version()}"

    def test_version_flag_does_not_require_fixture_files(self):
        project_root = Path(__file__).resolve().parents[1]
        result = _run("--version", cwd=project_root)
        assert result.returncode == 0
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestCLIHappyPath:
    @pytest.fixture(autouse=True)
    def require_fixtures(self):
        if not MOD_FOLDER.exists():
            pytest.skip("Fixture mod folder not present")

    def test_exit_code_1_when_problems_found(self):
        result = _run(str(MOD_FOLDER))
        # The real mod has known problems, so exit code must be 1
        assert result.returncode == 1

    def test_stdout_contains_problem_in_matcher_format(self):
        result = _run(str(MOD_FOLDER))
        # Format: path:line:column: warning: rule_id: message
        assert ":" in result.stdout
        assert "warning:" in result.stdout

    def test_stdout_contains_rule_id(self):
        result = _run(str(MOD_FOLDER))
        assert "unused-mapping-id" in result.stdout

    def test_stdout_shows_loading_progress(self):
        result = _run(str(MOD_FOLDER))
        assert "Loading and parsing files" in result.stdout


# ---------------------------------------------------------------------------
# Clean file (no problems expected)
# ---------------------------------------------------------------------------

class TestCLICleanFile:
    def test_exit_code_0_when_no_problems(self, tmp_path: Path):
        # Build a minimal valid mod folder
        mod = tmp_path / "MyMod"
        mod.mkdir()
        (mod / "clean.i3d").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<i3D>\n  <Scene>\n    <Shape name=\"myNode\"/>\n  </Scene>\n</i3D>\n",
            encoding="utf-8",
        )
        (mod / "clean.xml").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<vehicle>\n"
            "  <i3dMappings>\n"
            '    <i3dMapping id="myNode" node="0"/>\n'
            "  </i3dMappings>\n"
            '  <component node="myNode"/>\n'
            "</vehicle>\n",
            encoding="utf-8",
        )
        (mod / "modDesc.xml").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<modDesc>\n  <storeItems>\n"
            '    <storeItem xmlFilename="clean.xml"/>\n'
            "  </storeItems>\n</modDesc>\n",
            encoding="utf-8",
        )
        result = _run(str(mod))
        assert result.returncode == 0
        assert "No problems found" in result.stdout


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestCLIErrorHandling:
    def test_missing_folder_exits_nonzero(self, tmp_path: Path):
        result = _run(str(tmp_path / "does_not_exist"))
        assert result.returncode != 0

    def test_missing_folder_prints_error(self, tmp_path: Path):
        result = _run(str(tmp_path / "does_not_exist"))
        combined = result.stderr.lower() + result.stdout.lower()
        assert "error" in combined or "not found" in combined

    def test_missing_moddesc_exits_nonzero(self, tmp_path: Path):
        # tmp_path is a real dir but has no modDesc.xml
        result = _run(str(tmp_path))
        assert result.returncode != 0

    def test_missing_moddesc_prints_error(self, tmp_path: Path):
        result = _run(str(tmp_path))
        assert "error" in result.stderr.lower()

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

    def test_init_with_mod_folder_prefills_check_task_args(self, tmp_path: Path):
        # Create a minimal mod folder
        mod = tmp_path / "MyMod"
        mod.mkdir()
        (mod / "modDesc.xml").write_text(
            '<?xml version="1.0"?><modDesc><storeItems/></modDesc>',
            encoding="utf-8",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        result = _run(str(mod), "--init", cwd=workspace)
        assert result.returncode == 0
        tasks_data = json.loads((workspace / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        check_task = next(
            t for t in tasks_data["tasks"]
            if t.get("label") == "Check Mod (fs25-mod-checker)"
        )
        args = check_task.get("args") or []
        assert any(str(mod.resolve()) in a for a in args)

    def test_init_without_mod_folder_args_are_empty(self, tmp_path: Path):
        result = _run("--init", cwd=tmp_path)
        assert result.returncode == 0
        tasks_data = json.loads((tmp_path / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        check_task = next(
            t for t in tasks_data["tasks"]
            if t.get("label") == "Check Mod (fs25-mod-checker)"
        )
        # Without a mod_folder, args list should not contain a path
        args = [a for a in (check_task.get("args") or []) if not a.startswith("-")]
        assert args == []
