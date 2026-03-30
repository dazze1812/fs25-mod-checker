import json
import sys
import shutil
import zipfile
from pathlib import Path

from fs25_mod_checker.checker import deduplicate_problems, run_checks


def _create_mod_zip(workspace: Path, output_zip: Path | None = None) -> Path:
    """Create a ZIP package for the current mod workspace."""
    excluded_top_level = {
        ".git",
        ".vscode",
        ".pytest_cache",
        ".coverage",
        ".venv",
        "build",
        "dist",
        "fs25-mod-checker.spec",
        "FS25 Mod Checker.spec",
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
    """Resolve the fs25-mod-checker command for use in VS Code tasks.
    
    Returns: (command, args) tuple where command is the executable and args are additional arguments
    """
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


def _init_workspace() -> None:
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
    
    if not check_task:
        check_task = {
            "label": "Check Mod (fs25-mod-checker)",
            "type": "shell",
            "command": command,
            "args": command_args,
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
        # Update command and args for existing task, and migrate legacy arg forms.
        check_task["command"] = command
        existing_args = check_task.get("args") or []

        # If command is direct fs25-mod-checker executable, remove legacy
        # "-m fs25_mod_checker" prefix but keep any user XML/i3d args.
        if command_args == [] and len(existing_args) >= 2 and existing_args[:2] == ["-m", "fs25_mod_checker"]:
            check_task["args"] = existing_args[2:]
        elif not existing_args:
            check_task["args"] = command_args
    
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
    print(f"[OK] Created/updated .vscode/tasks.json")
    print()
    print("Next steps:")
    print("1. Edit .vscode/tasks.json and add the XML file path to the 'Check Mod' task args")
    print("2. Run 'Terminal > Run Task' to:")
    print("   - Check Mod (fs25-mod-checker) - validates i3dMappings")
    print("   - Package Mod (Create ZIP) - creates a release zip file")


def main() -> None:
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="fs25-mod-checker",
        description="Validates i3dMappings in FS25 mod files"
    )
    parser.add_argument(
        "xml_file",
        nargs="?",
        help="Path to the i3dMappings XML file (e.g., vehicles/MyMod/MyMod.xml)"
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize VS Code workspace with tasks"
    )
    parser.add_argument(
        "--i3d",
        dest="i3d_file",
        help="Optional path to the corresponding .i3d file"
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Create a ZIP package of the current workspace"
    )
    parser.add_argument(
        "--output",
        dest="output_zip",
        help="Optional output ZIP path used with --package"
    )
    
    args = parser.parse_args()
    
    if args.init:
        _init_workspace()
        return

    if args.package:
        zip_path = _create_mod_zip(Path.cwd(), Path(args.output_zip) if args.output_zip else None)
        print(f"[OK] Created {zip_path}")
        return
    
    if not args.xml_file:
        parser.print_help()
        sys.exit(2)
    
    xml_path = Path(args.xml_file)
    
    if not xml_path.exists():
        print(f"Error: File not found: {xml_path}", file=sys.stderr)
        sys.exit(1)
    
    # Use explicit i3d path when provided, otherwise infer from XML path.
    i3d_path = Path(args.i3d_file) if args.i3d_file else xml_path.with_suffix(".i3d")
    
    if not i3d_path.exists():
        print(f"Error: I3D file not found: {i3d_path}", file=sys.stderr)
        sys.exit(1)
    
    # Run all checks
    problems = run_checks(xml_path, i3d_path)
    
    # Output results in VS Code problem matcher format
    if problems:
        for problem in problems:
            print(f"{xml_path.resolve()}:{problem.line_number}:1: warning: {problem.rule_id}: {problem.message}")
        sys.exit(1)
    else:
        print(f"[OK] No problems found in {xml_path}")
