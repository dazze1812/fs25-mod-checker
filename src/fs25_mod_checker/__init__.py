import json
import shutil
import sys
import tomllib
import zipfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from .checker import run_checks_for_mod

PACKAGE_NAME = "fs25-mod-checker"


def _read_pyproject_version() -> str:
    """Read the project version from a nearby pyproject.toml when available."""
    candidates: list[Path] = []

    # Source-tree and editable install paths.
    this_file = Path(__file__).resolve()
    for parent in [this_file.parent, *this_file.parents]:
        candidates.append(parent / "pyproject.toml")

    # PyInstaller one-file extraction directory.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "pyproject.toml")

    seen: set[Path] = set()
    for pyproject_path in candidates:
        if pyproject_path in seen:
            continue
        seen.add(pyproject_path)
        if not pyproject_path.exists():
            continue
        pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        return pyproject_data["project"]["version"]

    raise FileNotFoundError("pyproject.toml not found")


def get_version() -> str:
    """Return the project version from local pyproject.toml or package metadata.

    Falls back to a safe default if neither is available, to avoid import-time
    failures in environments where metadata files are not bundled (e.g. PyInstaller).
    """
    try:
        return _read_pyproject_version()
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError):
        try:
            return package_version(PACKAGE_NAME)
        except PackageNotFoundError:
            # As a last resort, return a safe default instead of raising at import time.
            return "0.0.0"


__version__ = get_version()


def _create_mod_zip(workspace: Path, output_zip: Path | None = None) -> Path:
    """Create a ZIP package for the current mod workspace."""
    excluded_top_level = {
        ".git",
        ".vscode",
        ".venv",
        "venv",
        "dist",
        "build",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
        "htmlcov",
    }

    workspace = workspace.resolve()
    output_path = (output_zip or (workspace / f"{workspace.name}.zip")).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files_to_archive: list[Path] = []
    for entry in workspace.iterdir():
        if entry.name in excluded_top_level:
            continue
        if entry.suffix.lower() == ".zip":
            continue

        if entry.is_file():
            files_to_archive.append(entry)
            continue

        if entry.is_dir():
            for child in entry.rglob("*"):
                if child.is_file() and child.resolve() != output_path:
                    files_to_archive.append(child)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files_to_archive:
            archive.write(file_path, arcname=file_path.relative_to(workspace))

    return output_path


def _resolve_checker_command() -> tuple[str, list[str]]:
    """Resolve the checker command for VS Code tasks."""
    # If running as compiled executable (PyInstaller), return the exe path
    if getattr(sys, 'frozen', False):
        return (str(Path(sys.executable).resolve()), [])
    
    # Try to find fs25-mod-checker executable adjacent to python.exe
    python_dir = Path(sys.executable).parent
    for exe_name in ("fs25-mod-checker.exe", "fs25-mod-checker"):
        exe_path = python_dir / exe_name
        if exe_path.exists():
            return (str(exe_path.resolve()), [])
    
    # Fall back to python -m invocation
    python_cmd = shutil.which('python') or 'python'
    return (python_cmd, ["-m", "fs25_mod_checker"])


def _init_workspace(mod_folder: Path | None = None) -> None:
    """Initialize VS Code workspace with tasks for checking and packaging the mod."""
    cwd = Path.cwd()
    vscode_dir = cwd / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    
    tasks_file = vscode_dir / "tasks.json"
    
    # Load existing tasks or create new structure
    if tasks_file.exists():
        try:
            tasks_data = json.loads(tasks_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            tasks_data = {"version": "2.0.0", "tasks": []}
    else:
        tasks_data = {"version": "2.0.0", "tasks": []}
    
    if "tasks" not in tasks_data:
        tasks_data["tasks"] = []
    
    # Find existing "Check Mod" task
    check_task = None
    for task in tasks_data["tasks"]:
        if task.get("label") == "Check Mod (fs25-mod-checker)":
            check_task = task
            break
    
    # Resolve the checker command and args
    command, command_args = _resolve_checker_command()

    # Build args for the Check Mod task: base args + mod folder path.
    if mod_folder is not None:
        check_mod_args = [*command_args, str(mod_folder.resolve())]
    else:
        check_mod_args = list(command_args)

    if not check_task:
        check_task = {
            "label": "Check Mod (fs25-mod-checker)",
            "type": "shell",
            "command": command,
            "args": check_mod_args,
            "problemMatcher": [
                {
                    "name": "fs25-mod-checker",
                    "owner": "fs25-mod-checker",
                    "fileLocation": "absolute",
                    "pattern": {
                        "regexp": "^(.+?):(\\d+):(\\d+):\\s+(\\w+):\\s+([a-z-]+):\\s+(.*)$",
                        "file": 1,
                        "line": 2,
                        "column": 3,
                        "severity": 4,
                        "code": 5,
                        "message": 6
                    }
                }
            ],
            "group": {
                "kind": "test",
                "isDefault": False
            },
            "presentation": {
                "reveal": "always",
                "panel": "shared"
            }
        }
        tasks_data["tasks"].append(check_task)
    else:
        # Update command and always refresh args (including mod folder).
        check_task["command"] = command
        check_task["args"] = check_mod_args
    
    # Find existing "Package Mod" task
    package_task = None
    for task in tasks_data["tasks"]:
        if task.get("label") == "Package Mod (Create ZIP)":
            package_task = task
            break
    
    package_task_args = [*command_args, "--package"]

    if not package_task:
        package_task = {
            "label": "Package Mod (Create ZIP)",
            "type": "shell",
            "command": command,
            "args": package_task_args,
            "group": {
                "kind": "build",
                "isDefault": False
            },
            "presentation": {
                "reveal": "always",
                "panel": "shared"
            }
        }
        tasks_data["tasks"].append(package_task)
    else:
        package_task["command"] = command
        package_task["args"] = package_task_args
    
    # Write back the tasks.json
    tasks_file.write_text(json.dumps(tasks_data, indent=2), encoding="utf-8")
    
    print(f"[OK] Initialized VS Code workspace in {cwd}")
    print("[OK] Created/updated .vscode/tasks.json")
    print()
    print("Next steps:")
    if mod_folder is None:
        print("1. Edit .vscode/tasks.json and add the mod folder path to the 'Check Mod' task args")
    print("2. Run 'Terminal > Run Task' to:")
    print("   - Check Mod (fs25-mod-checker) - validates i3dMappings in the mod folder")
    print("   - Package Mod (Create ZIP) - creates a release zip file")


def main() -> None:
    """Main CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="fs25-mod-checker",
        description="Validates i3dMappings in all FS25 mod XML files listed in modDesc.xml"
    )
    parser.add_argument(
        "mod_folder",
        nargs="?",
        help="Path to the mod folder (must contain modDesc.xml)"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize VS Code workspace with tasks (uses mod_folder if provided)"
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Create a ZIP package of the current workspace"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--output",
        dest="output_zip",
        help="Optional output ZIP path used with --package"
    )

    args = parser.parse_args()

    if args.init:
        mod_folder_for_init = Path(args.mod_folder) if args.mod_folder else None
        _init_workspace(mod_folder_for_init)
        return

    if args.package:
        output_zip = Path(args.output_zip) if args.output_zip else None
        zip_path = _create_mod_zip(Path.cwd(), output_zip)
        print(f"[OK] Created {zip_path}")
        return

    if not args.mod_folder:
        parser.print_help()
        sys.exit(2)

    mod_folder = Path(args.mod_folder)

    if not mod_folder.exists():
        print(f"Error: Path not found: {mod_folder}", file=sys.stderr)
        sys.exit(1)

    if not mod_folder.is_dir():
        print(f"Error: Not a directory: {mod_folder}", file=sys.stderr)
        sys.exit(1)

    moddesc_path = mod_folder / "modDesc.xml"
    if not moddesc_path.exists():
        print(f"Error: modDesc.xml not found in: {mod_folder}", file=sys.stderr)
        sys.exit(1)

    # Run checks for all XML files listed in modDesc.xml.
    # The I3D path for each XML is read from the <filename> element inside the
    # XML, falling back to replacing the .xml suffix with .i3d.
    results = run_checks_for_mod(mod_folder)

    if not results:
        print(
            "Warning: No XML/I3D pairs were checked. "
            "All storeItem files may be missing or have no matching I3D.",
            file=sys.stderr,
        )
        sys.exit(1)

    has_problems = False
    for xml_path, problems in results:
        for problem in problems:
            print(
                f"{xml_path.resolve()}:{problem.line_number}:1: warning:"
                f" {problem.rule_id}: {problem.message}"
            )
            has_problems = True

    if has_problems:
        sys.exit(1)
    else:
        print(f"[OK] No problems found in {mod_folder}")
