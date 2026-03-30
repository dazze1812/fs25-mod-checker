# VS Code Problem Matcher Setup

This project can bootstrap VS Code tasks with built-in problem matcher support.

## Quick Start

1. Run:

```cmd
fs25-mod-checker --init
```

2. Open [.vscode/tasks.json](.vscode/tasks.json).
3. Set the XML path in the Check Mod task args.

Example:

```json
"args": ["vehicles/MyMod/MyMod.xml"]
```

4. Run the task: Terminal -> Run Task -> Check Mod (fs25-mod-checker)

Problems are parsed into the VS Code Problems panel.

## Output Format

The CLI emits diagnostics in this form:

```text
absolute\\path\\to\\file.xml:line:1: warning: rule-id: message
```

## Matcher Pattern

The default matcher pattern created by --init is:

```regex
^(.+?):(\\d+):(\\d+):\\s+(\\w+):\\s+([a-z-]+):\\s+(.*)$
```

Field mapping:

- file: 1
- line: 2
- column: 3
- severity: 4
- code: 5
- message: 6

## Troubleshooting

- No diagnostics in Problems panel:
  - Ensure fileLocation is absolute and CLI prints absolute paths.
  - Verify the task command points to fs25-mod-checker (or python -m fallback).
- XML path not set:
  - Add your XML path to args in the Check Mod task.
- Unexpected output shape:
  - If you change CLI format, update matcher regex in tasks.json accordingly.
