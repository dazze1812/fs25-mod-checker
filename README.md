# FS25 Mod Checker

Python CLI that validates i3dMappings in all FS25 mod XML files listed in modDesc.xml, with VS Code problem matcher support.

## Features

- Validates all i3dMappings in all XML files declared in modDesc.xml
- Checks that i3dMapping node paths exist in their corresponding I3D scene graphs
- Detects duplicate mapping IDs and duplicate mapped node paths
- Detects unused mappings and common name mismatches
- Detects references to non-existent mapping IDs or node paths
- Verifies that all referenced files in XML and I3D files exist in the mod folder
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

### Validate a mod folder

Run the checker on a mod folder that contains a modDesc.xml:

```cmd
fs25-mod-checker path\to\mod\folder
```

The checker automatically:
- Parses modDesc.xml to find all storeItem XML files
- For each XML file, derives the i3d filename (same stem, `.i3d` extension)
- Runs all checks on each file pair

Output format (VS Code matcher compatible):

```text
absolute\path\to\file.xml:line:1: warning: rule-id: message
```

Note: column is currently emitted as 1.

### Initialize VS Code tasks with mod folder

Initialize VS Code workspace tasks using the mod folder argument:

```cmd
fs25-mod-checker path\to\mod\folder --init
```

This creates or updates [.vscode/tasks.json](.vscode/tasks.json) with:

- Check Mod (fs25-mod-checker) — pre-filled with the mod folder path
- Package Mod (Create ZIP) — packages the current workspace

Without a mod folder argument, `--init` still works but doesn't pre-fill the mod path:

```cmd
fs25-mod-checker --init
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
| missing-reference-file | Referenced file in XML or I3D does not exist in mod folder |

## Development

Run tests:

```cmd
uv run pytest --cov
```

Run type checking:

```cmd
uv run pyright
```

Run checker on fixture mod folder:

```cmd
uv run fs25-mod-checker tests/fixtures/FS25_VolvoEWR150E_Fippe3DModding
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