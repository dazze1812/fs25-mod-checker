# fs25-mod-checker Agents

This document defines custom agents and specialized workflows for working with the **fs25-mod-checker** project using GitHub Copilot.

## Default Behavior

When working with this project, Copilot uses its default agent behavior unless specified otherwise. You can request features, debug issues, refactor code, or add tests using standard conversation.

## Recommended Use Cases

### Issue Investigation

**Request format:**
> Explore the codebase to understand why [specific check] is not working correctly.

Copilot will:
- Search for relevant functions in `checker.py`
- Examine test cases in `tests/`
- Identify edge cases or patterns

### Adding New Checks

**Request format:**
> Add a new check to detect [specific pattern] in i3dMappings. Create tests with fixture data.

Copilot will:
- Design the check function following existing patterns
- Add it to the check orchestration in `run_checks()`
- Create corresponding unit tests
- Update the rule IDs list

### VS Code Integration

**Request format:**
> Create a VS Code task to run the checker on [specific mod file] with problem matcher integration.

Copilot will:
- Update `.vscode/tasks.json` with a new task
- Ensure the regex pattern matches output format
- Test the task configuration

### Workspace Initialization

**Request format:**
> Set up a new FS25 mod project to use the checker in VS Code.

Copilot will help you run:
```cmd
fs25-mod-checker path\to\mod --init
```

This automatically creates `.vscode/tasks.json` with Check Mod and Package Mod tasks, with the Check Mod task pre-filled with the mod folder path.

Alternatively, without a mod folder:
```cmd
fs25-mod-checker --init
```

Then manually add the mod folder path to the Check Mod task args.

### Testing & Coverage

**Request format:**
> Improve test coverage for [module]. Show gaps and add tests.

Copilot will:
- Run `pytest --cov` to identify uncovered lines
- Write targeted unit or integration tests
- Ensure edge cases are handled

## Project Structure Reference

```
fs25-mod-checker/
├── src/fs25_mod_checker/
│   ├── __init__.py           # CLI entry point
│   ├── __main__.py           # Console script
│   └── checker.py            # All checking logic
├── tests/
│   ├── test_checker.py       # 48 unit tests
│   ├── test_integration.py   # CLI integration tests
│   └── fixtures/             # Real FS25 mod files
├── .vscode/
│   ├── tasks.json            # VS Code tasks
│   └── PROBLEM_MATCHER_SETUP.md
├── .github/
│   └── workflows/
│       └── ci.yml            # GitHub Actions CI (pytest)
├── scripts/
│   └── build.cmd             # PyInstaller build script
└── pyproject.toml            # Project config, test settings
```

## Key Files & Functions

### `src/fs25_mod_checker/checker.py` (Core Logic)

**Checks (all functions return `list[Problem]`):**
- `check_invalid_node_paths()` — Rule: `invalid-node-path`
- `check_duplicate_mapping_ids()` — Rule: `duplicate-mapping-id`
- `check_duplicate_node_paths()` — Rule: `duplicate-node-path`
- `check_unused_mappings()` — Rules: `unused-mapping-id*` (3 variants)
- `check_references()` — Rules: `reference-to-non-existent-*` (2 variants)
- `check_missing_reference_files()` — Rule: `missing-reference-file`

**Mod folder functions:**
- `load_xml_files_from_moddesc(Path) → list[Path]` — Parse modDesc.xml and return storeItem XML paths
- `run_checks_for_mod(Path) → list[tuple[Path, list[Problem]]]` — Run all checks for all XML files in mod

**Single file functions:**
- `load_i3d_nodes(Path) → dict[str, I3dNode]` — Parse I3D node structure
- `load_i3d_mappings(Path) → dict[str, I3dMapping]` — Parse XML mappings
- `run_checks(Path, Path, Path) → list[Problem]` — Orchestrate all checks for one XML/i3d pair

**Data Classes:**
- `Problem(rule_id, line_number, message)`
- `I3dNode(path, name)`
- `I3dMapping(id, node, normalized_node, line_number)`

### `src/fs25_mod_checker/__init__.py` (CLI)

Entry point: `main()` — Parses args, runs checks, prints results in problem matcher format.

### `tests/`

- `test_checker.py` — 66 unit tests covering all check functions and mod folder utilities; 98% coverage on checker.py
- `test_integration.py` — 20 integration tests running the CLI entry point with various mod folder scenarios
- `fixtures/FS25_VolvoEWR150E_Fippe3DModding/` — Real FS25 mod fixture with minimal referenced files

## Common Tasks

### Add a New Rule

1. Create a `check_*` function in `checker.py` that returns `list[Problem]`
2. Add it to `run_checks()` orchestration
3. Add 5-10 unit tests in `test_checker.py`
4. Document the rule ID in `README.md` rule table

**Example:**
```python
def check_my_new_rule(xml_lines: list[str], ...) -> list[Problem]:
    problems = []
    # Logic here
    return problems
```

### Fix or Extend Output Format

- Adjust format string in `src/fs25_mod_checker/__init__.py:main()` (line ~256)
- Update regex in `.vscode/tasks.json` to match
- Sync regex in [PROBLEM_MATCHER_SETUP.md](.vscode/PROBLEM_MATCHER_SETUP.md)
- Add integration tests for the new format

### Update Problem Matcher for VS Code

- Edit pattern in `.vscode/tasks.json`
- Test by running a task and checking the **Problems** panel
- Update documentation in `tasks.json` and `.vscode/PROBLEM_MATCHER_SETUP.md`

### Initialize New Workspace

Run from the root of a FS25 mod project (with modDesc.xml):

```cmd
fs25-mod-checker . --init
```

This:
1. Creates `.vscode/` directory if not present
2. Generates/updates `tasks.json` with Check Mod and Package Mod tasks
3. Pre-fills the Check Mod task with the current folder path
4. Embeds problem matcher regex for parsing output
5. Prints next steps and run instructions

You can immediately run the Check Mod task without editing.

## Testing Strategies

### Unit Tests (Fast, Isolated)

Use minimal fixture data:
```python
nodes = _nodes(("0", "root"), ("0|1", "child"))
mappings = {"test": _mapping("test", "0|1")}
```

### Integration Tests (Real Binary)

Test CLI behavior by running the entry point as a subprocess.

### Real Fixture Tests

Uses `tests/fixtures/FS25_VolvoEWR150E_Fippe3DModding/` — a real FS25 mod with modDesc.xml and all referenced XML/i3D files. Non-XML/i3D files are empty stubs to minimize repository size.

## Dependencies

- **Runtime:** Python 3.12+, standard library only
- **Dev:** pytest, pytest-cov, pyinstaller
- **Managed via:** `uv` (uv.lock, pyproject.toml)

## Build & Release

```bash
# Build Windows executable
scripts/build.cmd

# Build Python package
uv build

# Run tests
uv run pytest --cov

# Install locally
uv pip install -e .
```

Output binary name: `fs25-mod-checker.exe` (in `dist/`)

## Performance Notes

- Parsing I3D XML: `O(n_nodes)` — fast for typical mods
- Parsing mappings: `O(n_mappings)` — linear scan
- Unused mapping check: `O(n_mappings × n_lines)` — uses regex matching
- Missing file references: `O(n_refs × mod_files)` — disk access for each reference
- Total across all XML files in mod: ~1-2 seconds for typical mid-size mods

## Version & Release Info

- **Current version:** 0.1.0
- **Python requirement:** >=3.12
- **Project type:** CLI tool / Python package
- **Build tool:** PyInstaller → single Windows exe
