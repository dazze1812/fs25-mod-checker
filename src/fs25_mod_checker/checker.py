"""Core logic for checking FS25 mod i3dMappings for problems."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET


@dataclass
class Problem:
    rule_id: str
    line_number: int
    message: str


@dataclass
class I3dNode:
    path: str
    name: str


@dataclass
class I3dMapping:
    id: str
    node: str
    normalized_node: str
    line_number: int


_NODE_REF_ATTRS = ["node", "linkNode", "repr", "driveNode", "rootNode", "cameraNode"]
_NODE_REF_PATTERN = re.compile(
    r"(" + "|".join(re.escape(a) for a in _NODE_REF_ATTRS) + r')="([^"]+)"'
)
_I3D_MAPPING_LINE_PATTERN = re.compile(r"<i3dMapping")
_MAPPING_ID_PATTERN = re.compile(r'id="([^"]+)"')
_MAPPING_NODE_PATTERN = re.compile(r'node="([^"]+)"')


def _normalize_node_path(path: str) -> str:
    """Convert '>' separators to '|' and strip trailing '>'."""
    if not path:
        return ""
    if ">" in path:
        path = path.rstrip(">").replace(">", "|")
    return path


def _build_node_map(element: Any, current_path: str, node_map: dict[str, I3dNode]) -> None:
    for i, child in enumerate(element):
        child_path = str(i) if not current_path else f"{current_path}|{i}"
        node_map[child_path] = I3dNode(path=child_path, name=child.get("name", ""))
        _build_node_map(child, child_path, node_map)


def load_i3d_nodes(i3d_path: Path) -> dict[str, I3dNode]:
    try:
        tree = ET.parse(i3d_path)
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"Failed to parse I3D file {i3d_path}: {exc}") from exc
    root = tree.getroot()
    if root is None:
        raise ValueError(f"No root element found in {i3d_path}")
    scene = root.find("Scene")
    if scene is None:
        raise ValueError(f"No <Scene> element found in {i3d_path}")
    node_map: dict[str, I3dNode] = {}
    for root_idx, child in enumerate(scene):
        root_path = str(root_idx)
        node_map[root_path] = I3dNode(path=root_path, name=child.get("name", ""))
        _build_node_map(child, root_path, node_map)
    return node_map


def load_i3d_mappings(xml_path: Path) -> dict[str, I3dMapping]:
    """Return mappings keyed by ID. Duplicates are tracked for check 2 separately."""
    mappings: dict[str, I3dMapping] = {}
    lines = xml_path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not _I3D_MAPPING_LINE_PATTERN.search(line):
            continue
        id_m = _MAPPING_ID_PATTERN.search(line)
        if not id_m:
            continue
        node_m = _MAPPING_NODE_PATTERN.search(line)
        node_path = node_m.group(1) if node_m else ""
        mapping_id = id_m.group(1)
        mappings[mapping_id] = I3dMapping(
            id=mapping_id,
            node=node_path,
            normalized_node=_normalize_node_path(node_path),
            line_number=line_number,
        )
    return mappings


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_invalid_node_paths(
    mappings: dict[str, I3dMapping], i3d_nodes: dict[str, I3dNode]
) -> list[Problem]:
    """Check 1: i3dMapping entries that reference non-existent I3D node paths."""
    problems = []
    for mapping in mappings.values():
        if mapping.normalized_node not in i3d_nodes:
            problems.append(Problem(
                rule_id="invalid-node-path",
                line_number=mapping.line_number,
                message=f"i3dMapping '{mapping.id}' points to a non-existent node path '{mapping.node}'.",
            ))
    return problems


def check_duplicate_mapping_ids(xml_path: Path) -> list[Problem]:
    """Check 2: i3dMapping IDs defined more than once."""
    problems = []
    occurrences: dict[str, list[int]] = defaultdict(list)
    lines = xml_path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not _I3D_MAPPING_LINE_PATTERN.search(line):
            continue
        m = _MAPPING_ID_PATTERN.search(line)
        if m:
            occurrences[m.group(1)].append(line_number)
    for mapping_id, line_numbers in occurrences.items():
        if len(line_numbers) > 1:
            for ln in line_numbers:
                problems.append(Problem(
                    rule_id="duplicate-mapping-id",
                    line_number=ln,
                    message=f"Duplicate i3dMapping ID found: '{mapping_id}'. This ID is defined multiple times.",
                ))
    return problems


def check_duplicate_node_paths(mappings: dict[str, I3dMapping]) -> list[Problem]:
    """Check 3: Multiple mapping IDs pointing to the same I3D node path."""
    problems = []
    by_path: dict[str, list[I3dMapping]] = defaultdict(list)
    for mapping in mappings.values():
        if mapping.normalized_node:
            by_path[mapping.normalized_node].append(mapping)
    for _path, group in by_path.items():
        if len(group) > 1:
            ids = "', '".join(m.id for m in group)
            for mapping in group:
                problems.append(Problem(
                    rule_id="duplicate-node-path",
                    line_number=mapping.line_number,
                    message=(
                        f"The node path '{mapping.node}' is mapped by multiple IDs: '{ids}'."
                    ),
                ))
    return problems


def check_unused_mappings(
    mappings: dict[str, I3dMapping],
    i3d_nodes: dict[str, I3dNode],
    xml_lines: list[str],
) -> list[Problem]:
    """Check 4: Mapping IDs that are defined but never referenced elsewhere in the XML."""
    problems = []
    for mapping in mappings.values():
        mapping_id = mapping.id
        # Build a per-word pattern so partial substring matches are excluded.
        id_regex = re.compile(r'=\s*"[^"]*\b' + re.escape(mapping_id) + r'\b[^"]*"')
        used = any(
            id_regex.search(line)
            for ln, line in enumerate(xml_lines, start=1)
            if ln != mapping.line_number  # skip the definition line itself
        )
        if used:
            continue
        resolved = i3d_nodes.get(mapping.normalized_node)
        if resolved is None:
            problems.append(Problem(
                rule_id="unused-mapping-id-invalid-node",
                line_number=mapping.line_number,
                message=(
                    f"Unused i3dMapping ID '{mapping_id}'. "
                    f"The node path '{mapping.node}' is also invalid."
                ),
            ))
        elif resolved.name and resolved.name != mapping_id:
            problems.append(Problem(
                rule_id="unused-mapping-id-name-mismatch",
                line_number=mapping.line_number,
                message=(
                    f"Unused i3dMapping ID '{mapping_id}'. "
                    f"The node it points to is named '{resolved.name}', "
                    f"which does not match the ID."
                ),
            ))
        else:
            problems.append(Problem(
                rule_id="unused-mapping-id",
                line_number=mapping.line_number,
                message=f"Unused i3dMapping ID '{mapping_id}'. It is defined but never referenced.",
            ))
    return problems


def check_references(
    xml_lines: list[str],
    mappings: dict[str, I3dMapping],
    i3d_nodes: dict[str, I3dNode],
) -> list[Problem]:
    """Check 5: node-reference attributes that point to non-existent paths or mapping IDs."""
    problems = []
    for line_number, line in enumerate(xml_lines, start=1):
        if line.lstrip().startswith("<i3dMapping"):
            continue
        for match in _NODE_REF_PATTERN.finditer(line):
            attr_name = match.group(1)
            ref_value = match.group(2).strip()
            if not ref_value:  # pragma: no cover  # regex [^"]+ already prevents empty
                continue
            if ">" in ref_value or "|" in ref_value:
                # Direct path reference
                normalized = _normalize_node_path(ref_value)
                if normalized not in i3d_nodes:
                    problems.append(Problem(
                        rule_id="reference-to-non-existent-path",
                        line_number=line_number,
                        message=(
                            f"The attribute '{attr_name}' references a non-existent "
                            f"node path: '{ref_value}'."
                        ),
                    ))
            else:
                # Mapping ID reference
                if ref_value not in mappings:
                    problems.append(Problem(
                        rule_id="reference-to-non-existent-id",
                        line_number=line_number,
                        message=(
                            f"The attribute '{attr_name}' references a non-existent "
                            f"i3dMapping ID: '{ref_value}'."
                        ),
                    ))
    return problems


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def deduplicate_problems(problems: list[Problem]) -> list[Problem]:
    seen: set[tuple[int, str]] = set()
    unique: list[Problem] = []
    for p in sorted(problems, key=lambda x: (x.line_number, x.message)):
        key = (p.line_number, p.message)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _extract_file_references_from_xml(xml_lines: list[str]) -> dict[str, list[int]]:
    """Extract file paths from XML attributes and elements.
    
    Returns a dict mapping file path to list of line numbers where it appears.
    Filters out paths starting with $ (like $data) as those are in base game.
    """
    refs: dict[str, list[int]] = defaultdict(list)
    # Pattern to match filename="..." or file="..." or similar attributes
    attr_pattern = re.compile(r'(?:filename|file|src)="([^"]+)"')
    # Pattern to match <image>path</image>, <filename>path</filename>, etc.
    elem_pattern = re.compile(r'<(?:image|filename)>([^<]+)</(?:image|filename)>')
    
    for line_number, line in enumerate(xml_lines, start=1):
        # Extract attribute references
        for match in attr_pattern.finditer(line):
            path = match.group(1)
            # Skip game data paths and empty paths
            if path and not path.startswith("$"):
                refs[path].append(line_number)
        # Extract element text references
        for match in elem_pattern.finditer(line):
            path = match.group(1)
            # Skip game data paths and empty paths
            if path and not path.startswith("$"):
                refs[path].append(line_number)
    
    return refs


def _extract_file_references_from_i3d(i3d_path: Path) -> dict[str, list[int]]:
    """Extract file paths from I3D <Files>/<File filename="..."> elements.

    Returns a dict mapping file path to list of line numbers where it appears.
    Filters out paths starting with $ (like $data) as those are in base game.
    Uses XML parsing so that the I3D's declared encoding is respected.
    """
    refs: dict[str, list[int]] = defaultdict(list)

    try:
        # Let the XML parser handle encoding based on the XML declaration.
        tree = ET.parse(i3d_path)
    except ET.ParseError:
        # If the I3D is not well-formed XML, fall back to no references.
        return refs

    root = tree.getroot()

    # Iterate over all <Files>/<File> elements and collect filename attributes.
    for files_elem in root.findall(".//Files"):
        for file_elem in files_elem.findall("File"):
            filename = file_elem.get("filename")
            # Skip game data paths and empty paths
            if not filename or filename.startswith("$"):
                continue
            # sourceline is an lxml-specific attribute; standard-library parsers
            # (including defusedxml) do not set it, so we fall back to 1.
            line_no = getattr(file_elem, "sourceline", 1)
            refs[filename].append(line_no)

    return refs


def check_missing_reference_files(
    xml_path: Path,
    i3d_path: Path,
    mod_folder: Path,
) -> list[Problem]:
    """Check 6: Verify that all referenced files exist in the mod folder.
    
    Extracts file paths from both XML and I3D files and checks if they exist.
    Ignores paths starting with $ (game base data).
    """
    problems: list[Problem] = []
    xml_lines = xml_path.read_text(encoding="utf-8").splitlines()
    
    # Get all file references from XML
    xml_refs = _extract_file_references_from_xml(xml_lines)
    
    # Get all file references from I3D
    i3d_refs = _extract_file_references_from_i3d(i3d_path)
    
    # Check XML references
    for file_path, line_numbers in xml_refs.items():
        full_path = mod_folder / file_path
        if not full_path.exists():
            # Report on the first line where this file is referenced
            problems.append(Problem(
                rule_id="missing-reference-file",
                line_number=line_numbers[0],
                message=f"Referenced file not found: '{file_path}'",
            ))
    
    # Check I3D references.
    # I3D file paths are relative to the I3D file's own directory, so resolve
    # them against i3d_path.parent.  Only report a problem if the path resolves
    # to somewhere inside mod_folder (paths escaping the mod root are base-game
    # assets and should be silently skipped).
    mod_folder_resolved = mod_folder.resolve()
    i3d_dir = i3d_path.parent.resolve()
    for file_path, _ in i3d_refs.items():
        full_path = (i3d_dir / file_path).resolve()
        try:
            full_path.relative_to(mod_folder_resolved)
        except ValueError:
            # Path escapes the mod folder – treat as an external/game asset.
            continue
        if not full_path.exists():
            problems.append(Problem(
                rule_id="missing-reference-file",
                line_number=1,  # I3D line numbers are not mapped to XML lines
                message=f"Referenced file in I3D not found: '{file_path}'",
            ))
    
    return problems


def run_checks(xml_path: Path, i3d_path: Path, mod_folder: Path | None = None) -> list[Problem]:
    print("Loading and parsing files...")
    i3d_nodes = load_i3d_nodes(i3d_path)
    mappings = load_i3d_mappings(xml_path)
    xml_lines = xml_path.read_text(encoding="utf-8").splitlines()
    print(f"Found {len(i3d_nodes)} nodes in I3D and {len(mappings)} mappings in XML.")

    problems: list[Problem] = []

    print("1. Checking for i3dMapping entries with invalid node paths...")
    problems.extend(check_invalid_node_paths(mappings, i3d_nodes))

    print("2. Checking for duplicate mapping IDs...")
    problems.extend(check_duplicate_mapping_ids(xml_path))

    print("3. Checking for duplicate node paths in mappings...")
    problems.extend(check_duplicate_node_paths(mappings))

    print("4. Checking for unused mapping IDs and name mismatches...")
    problems.extend(check_unused_mappings(mappings, i3d_nodes, xml_lines))

    print("5. Checking for references to non-existent mappings or paths...")
    problems.extend(check_references(xml_lines, mappings, i3d_nodes))

    if mod_folder is not None:
        print("6. Checking for missing reference files in the mod folder...")
        problems.extend(check_missing_reference_files(xml_path, i3d_path, mod_folder))

    return problems


def _extract_i3d_path_from_xml(xml_path: Path, mod_folder: Path) -> Path | None:
    """Try to find the main I3D file path declared in the XML's <filename> element.

    Returns the resolved absolute path if found, or None if not found.
    The ``<filename>`` text is treated as relative to ``mod_folder``.
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return None
    root = tree.getroot()
    for elem in root.iter("filename"):
        text = (elem.text or "").strip()
        if text.lower().endswith(".i3d"):
            return mod_folder / text
    return None


def load_xml_files_from_moddesc(mod_folder: Path) -> list[Path]:
    """Parse modDesc.xml and return absolute paths of all storeItem XML files."""
    moddesc_path = mod_folder / "modDesc.xml"
    if not moddesc_path.exists():
        raise ValueError(f"No modDesc.xml found in {mod_folder}")
    try:
        tree = ET.parse(moddesc_path)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse modDesc.xml: {exc}") from exc
    root = tree.getroot()
    if root is None:
        raise ValueError(f"No root element found in {moddesc_path}")
    xml_files: list[Path] = []
    for store_item in root.iter("storeItem"):
        filename = store_item.get("xmlFilename")
        if filename:
            xml_files.append(mod_folder / filename)
    return xml_files


def run_checks_for_mod(mod_folder: Path) -> list[tuple[Path, list[Problem]]]:
    """Run all checks for all storeItem XML files declared in modDesc.xml.

    For each XML file the I3D path is read from the ``<filename>`` element
    inside the XML.  If no such element is present, the I3D path falls back to
    replacing the ``.xml`` suffix with ``.i3d``.  Files whose XML or I3D
    counterpart is missing are skipped with a warning.
    """
    xml_files = load_xml_files_from_moddesc(mod_folder)
    results: list[tuple[Path, list[Problem]]] = []
    for xml_path in xml_files:
        if not xml_path.exists():
            print(f"Warning: XML file not found, skipping: {xml_path}")
            continue
        i3d_path = _extract_i3d_path_from_xml(xml_path, mod_folder) or xml_path.with_suffix(".i3d")
        if not i3d_path.exists():
            print(f"Warning: I3D file not found, skipping: {i3d_path}")
            continue
        print(f"\nChecking {xml_path.name}...")
        problems = run_checks(xml_path, i3d_path, mod_folder)
        results.append((xml_path, problems))
    return results
