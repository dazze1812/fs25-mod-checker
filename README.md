# FS25 Mod Checker

Python CLI that validates i3dMappings in FS25 mod XML files, with VS Code problem matcher support.

## Features

- Validates i3dMapping node paths against the I3D scene graph
- Detects duplicate mapping IDs and duplicate mapped paths
- Detects unused mappings and common name mismatches
- Detects references to non-existent mapping IDs or node paths
- VS Code task and problem matcher bootstrap via --init
- Built-in mod ZIP packaging via --package

## Requirements

- Python 3.12+
- Optional: uv for local development workflows

## Installation

Install from source in editable mode:

```cmd
uv sync
```

Or with pip:

```cmd
pip install -e .
```

## Usage

### Validate a mod XML

```cmd
fs25-mod-checker path\to\vehicle.xml
```

Optional explicit I3D file:

```cmd
fs25-mod-checker path\to\vehicle.xml --i3d path\to\vehicle.i3d
```

Output format (VS Code matcher compatible):

```text
absolute\path\to\file.xml:line:1: warning: rule-id: message
```

Note: column is currently emitted as 1.

### Initialize VS Code tasks

From your mod project root:

```cmd
fs25-mod-checker --init
```

This creates or updates [.vscode/tasks.json](.vscode/tasks.json) with:

- Check Mod (fs25-mod-checker)
- Package Mod (Create ZIP)

Then set your XML file path in task args, for example:

```json
"args": ["vehicles/MyMod/MyMod.xml"]
```

More details: [.vscode/PROBLEM_MATCHER_SETUP.md](.vscode/PROBLEM_MATCHER_SETUP.md)

### Package the current workspace as ZIP

```cmd
fs25-mod-checker --package
```

Optional output path:

```cmd
fs25-mod-checker --package --output .\releases\MyMod.zip
```

### Show the checker version

```cmd
fs25-mod-checker --version
```

## Rule IDs

| Code | Description |
|------|-------------|
| invalid-node-path | i3dMapping points to a non-existent I3D node |
| duplicate-mapping-id | Same i3dMapping ID defined multiple times |
| duplicate-node-path | Multiple IDs map to the same I3D node path |
| unused-mapping-id | Mapping defined but never referenced |
| unused-mapping-id-invalid-node | Unused mapping with invalid node path |
| unused-mapping-id-name-mismatch | Unused mapping where node name does not match ID |
| reference-to-non-existent-id | Attribute references a non-existent mapping ID |
| reference-to-non-existent-path | Attribute references a non-existent I3D path |

## Development

Run tests:

```cmd
uv run pytest --cov
```

Run type checking:

```cmd
uv run pyright
```

Run checker on fixture:

```cmd
uv run fs25-mod-checker tests/fixtures/VolvoEWR150E.xml
```

Build Windows executable:

```cmd
scripts\build.cmd
```

Build Python package:

```cmd
uv build
```

## GitHub Upload Checklist

1. Ensure tests pass locally.
2. Ensure any release tag matches the version in [pyproject.toml](pyproject.toml).
3. Commit all changes.
4. Push to GitHub.

Example:

```cmd
git add .
git commit -m "Prepare docs, license, and CI"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).