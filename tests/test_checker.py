"""Unit tests for fs25_mod_checker.checker module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from fs25_mod_checker.checker import (
    I3dMapping,
    I3dNode,
    Problem,
    _normalize_node_path,
    check_duplicate_mapping_ids,
    check_duplicate_node_paths,
    check_invalid_node_paths,
    check_references,
    check_unused_mappings,
    deduplicate_problems,
    load_i3d_mappings,
    load_i3d_nodes,
    run_checks,
)

FIXTURES = Path(__file__).parent / "fixtures"
REAL_XML = FIXTURES / "VolvoEWR150E.xml"
REAL_I3D = FIXTURES / "VolvoEWR150E.i3d"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _minimal_i3d(tmp_path: Path, nodes: list[tuple[str, str | None]]) -> Path:
    """
    Build a minimal .i3d with a <Scene> containing root-level <Shape> nodes.
    ``nodes`` is a list of (index_path, name_or_None) tuples.
    Only flat root-level nodes are supported here for simplicity.
    """
    children_xml = ""
    for _path, name in nodes:
        name_attr = f' name="{name}"' if name else ""
        children_xml += f'  <Shape{name_attr}/>\n'
    content = f"""\
<?xml version="1.0" encoding="utf-8"?>
<i3D>
  <Scene>
{children_xml}  </Scene>
</i3D>
"""
    p = tmp_path / "test.i3d"
    p.write_text(content, encoding="utf-8")
    return p


def _nodes(*args: tuple[str, str]) -> dict[str, I3dNode]:
    return {path: I3dNode(path=path, name=name) for path, name in args}


def _mapping(mapping_id: str, node: str, line_number: int = 10) -> I3dMapping:
    from fs25_mod_checker.checker import _normalize_node_path as _n
    return I3dMapping(id=mapping_id, node=node, normalized_node=_n(node), line_number=line_number)


# ===========================================================================
# _normalize_node_path
# ===========================================================================

class TestNormalizeNodePath:
    def test_empty_string(self):
        assert _normalize_node_path("") == ""

    def test_plain_index(self):
        assert _normalize_node_path("0") == "0"

    def test_pipe_separator_unchanged(self):
        assert _normalize_node_path("0|1|2") == "0|1|2"

    def test_gt_separator_converted(self):
        assert _normalize_node_path("0>1>2") == "0|1|2"

    def test_trailing_gt_stripped(self):
        assert _normalize_node_path("0>1>") == "0|1"

    def test_mixed_separators_converted(self):
        # powershell normalises > consistently; our impl handles the same
        assert _normalize_node_path("0>1>2>") == "0|1|2"


# ===========================================================================
# load_i3d_nodes
# ===========================================================================

class TestLoadI3dNodes:
    def test_single_root_node(self, tmp_path: Path):
        i3d = _minimal_i3d(tmp_path, [("0", "root")])
        nodes = load_i3d_nodes(i3d)
        assert "0" in nodes
        assert nodes["0"].name == "root"

    def test_multiple_root_nodes(self, tmp_path: Path):
        i3d = _minimal_i3d(tmp_path, [("0", "a"), ("1", "b"), ("2", "c")])
        nodes = load_i3d_nodes(i3d)
        assert set(nodes.keys()) == {"0", "1", "2"}

    def test_nested_nodes_indexed(self, tmp_path: Path):
        content = """\
<?xml version="1.0" encoding="utf-8"?>
<i3D>
  <Scene>
    <Shape name="root">
      <Shape name="child0"/>
      <Shape name="child1"/>
    </Shape>
  </Scene>
</i3D>
"""
        p = tmp_path / "nested.i3d"
        p.write_text(content, encoding="utf-8")
        nodes = load_i3d_nodes(p)
        assert "0" in nodes
        assert nodes["0"].name == "root"
        assert "0|0" in nodes
        assert nodes["0|0"].name == "child0"
        assert "0|1" in nodes
        assert nodes["0|1"].name == "child1"

    def test_missing_scene_raises(self, tmp_path: Path):
        p = tmp_path / "bad.i3d"
        p.write_text('<i3D></i3D>', encoding="utf-8")
        with pytest.raises(ValueError, match="No <Scene>"):
            load_i3d_nodes(p)

    def test_node_without_name_attribute(self, tmp_path: Path):
        i3d = _minimal_i3d(tmp_path, [("0", None)])
        nodes = load_i3d_nodes(i3d)
        assert nodes["0"].name == ""


# ===========================================================================
# load_i3d_mappings
# ===========================================================================

class TestLoadI3dMappings:
    def test_basic_mapping_loaded(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMappings>
                <i3dMapping id="myNode" node="0|1"/>
              </i3dMappings>
            </root>
        """)
        mappings = load_i3d_mappings(xml)
        assert "myNode" in mappings
        m = mappings["myNode"]
        assert m.id == "myNode"
        assert m.node == "0|1"
        assert m.normalized_node == "0|1"

    def test_gt_path_normalised(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMapping id="x" node="0>1>2"/>
            </root>
        """)
        mappings = load_i3d_mappings(xml)
        assert mappings["x"].normalized_node == "0|1|2"

    def test_duplicate_id_last_one_wins(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMapping id="dup" node="0"/>
              <i3dMapping id="dup" node="1"/>
            </root>
        """)
        mappings = load_i3d_mappings(xml)
        # dict keeps last value for the key
        assert mappings["dup"].node == "1"

    def test_no_mappings(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", "<root/>")
        assert load_i3d_mappings(xml) == {}


# ===========================================================================
# check_invalid_node_paths  (Check 1)
# ===========================================================================

class TestCheckInvalidNodePaths:
    def test_valid_mapping_no_problem(self):
        nodes = _nodes(("0", "root"))
        mappings = {"root": _mapping("root", "0")}
        assert check_invalid_node_paths(mappings, nodes) == []

    def test_invalid_path_reported(self):
        nodes = _nodes(("0", "root"))
        mappings = {"missing": _mapping("missing", "99")}
        problems = check_invalid_node_paths(mappings, nodes)
        assert len(problems) == 1
        assert problems[0].rule_id == "invalid-node-path"
        assert "missing" in problems[0].message
        assert "99" in problems[0].message

    def test_empty_node_path_is_invalid(self):
        nodes = _nodes(("0", "root"))
        mappings = {"noNode": _mapping("noNode", "")}
        problems = check_invalid_node_paths(mappings, nodes)
        assert len(problems) == 1

    def test_multiple_invalid_paths(self):
        nodes: dict[str, I3dNode] = {}
        mappings = {
            "a": _mapping("a", "1"),
            "b": _mapping("b", "2"),
        }
        problems = check_invalid_node_paths(mappings, nodes)
        assert len(problems) == 2


# ===========================================================================
# check_duplicate_mapping_ids  (Check 2)
# ===========================================================================

class TestCheckDuplicateMappingIds:
    def test_no_duplicates(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMapping id="a" node="0"/>
              <i3dMapping id="b" node="1"/>
            </root>
        """)
        assert check_duplicate_mapping_ids(xml) == []

    def test_duplicate_reported(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMapping id="dup" node="0"/>
              <i3dMapping id="dup" node="1"/>
            </root>
        """)
        problems = check_duplicate_mapping_ids(xml)
        assert len(problems) == 2
        assert all(p.rule_id == "duplicate-mapping-id" for p in problems)
        assert all("dup" in p.message for p in problems)

    def test_three_duplicates_all_reported(self, tmp_path: Path):
        xml = _write(tmp_path, "test.xml", """\
            <root>
              <i3dMapping id="x" node="0"/>
              <i3dMapping id="x" node="1"/>
              <i3dMapping id="x" node="2"/>
            </root>
        """)
        problems = check_duplicate_mapping_ids(xml)
        assert len(problems) == 3


# ===========================================================================
# check_duplicate_node_paths  (Check 3)
# ===========================================================================

class TestCheckDuplicateNodePaths:
    def test_unique_paths_no_problem(self):
        mappings = {
            "a": _mapping("a", "0"),
            "b": _mapping("b", "1"),
        }
        assert check_duplicate_node_paths(mappings) == []

    def test_duplicate_path_reported(self):
        mappings = {
            "a": _mapping("a", "0"),
            "b": _mapping("b", "0"),
        }
        problems = check_duplicate_node_paths(mappings)
        assert len(problems) == 2
        assert all(p.rule_id == "duplicate-node-path" for p in problems)

    def test_empty_node_path_not_checked(self):
        mappings = {
            "a": _mapping("a", ""),
            "b": _mapping("b", ""),
        }
        # Empty paths are excluded from duplicate check
        assert check_duplicate_node_paths(mappings) == []


# ===========================================================================
# check_unused_mappings  (Check 4)
# ===========================================================================

class TestCheckUnusedMappings:
    def _xml_lines(self, content: str) -> list[str]:
        return textwrap.dedent(content).splitlines()

    def test_used_mapping_no_problem(self):
        mappings = {"bodyPart": _mapping("bodyPart", "0", line_number=2)}
        nodes = _nodes(("0", "bodyPart"))
        xml_lines = self._xml_lines("""\
            <root>
              <i3dMapping id="bodyPart" node="0"/>
              <component node="bodyPart"/>
            </root>
        """)
        assert check_unused_mappings(mappings, nodes, xml_lines) == []

    def test_unused_with_valid_node_and_matching_name(self):
        mappings = {"bodyPart": _mapping("bodyPart", "0", line_number=2)}
        nodes = _nodes(("0", "bodyPart"))
        xml_lines = self._xml_lines("""\
            <root>
              <i3dMapping id="bodyPart" node="0"/>
            </root>
        """)
        problems = check_unused_mappings(mappings, nodes, xml_lines)
        assert len(problems) == 1
        assert problems[0].rule_id == "unused-mapping-id"

    def test_unused_with_name_mismatch(self):
        mappings = {"myId": _mapping("myId", "0", line_number=2)}
        nodes = _nodes(("0", "differentName"))
        xml_lines = self._xml_lines("""\
            <root>
              <i3dMapping id="myId" node="0"/>
            </root>
        """)
        problems = check_unused_mappings(mappings, nodes, xml_lines)
        assert len(problems) == 1
        assert problems[0].rule_id == "unused-mapping-id-name-mismatch"
        assert "differentName" in problems[0].message

    def test_unused_with_invalid_node(self):
        mappings = {"myId": _mapping("myId", "99", line_number=2)}
        nodes: dict[str, I3dNode] = {}
        xml_lines = self._xml_lines("""\
            <root>
              <i3dMapping id="myId" node="99"/>
            </root>
        """)
        problems = check_unused_mappings(mappings, nodes, xml_lines)
        assert len(problems) == 1
        assert problems[0].rule_id == "unused-mapping-id-invalid-node"

    def test_partial_id_match_not_counted_as_used(self):
        # "arm" should not be counted as used if only "armLeft" appears
        mappings = {"arm": _mapping("arm", "0", line_number=2)}
        nodes = _nodes(("0", "arm"))
        xml_lines = self._xml_lines("""\
            <root>
              <i3dMapping id="arm" node="0"/>
              <component node="armLeft"/>
            </root>
        """)
        problems = check_unused_mappings(mappings, nodes, xml_lines)
        assert len(problems) == 1
        assert problems[0].rule_id == "unused-mapping-id"


# ===========================================================================
# check_references  (Check 5)
# ===========================================================================

class TestCheckReferences:
    def _lines(self, content: str) -> list[str]:
        return textwrap.dedent(content).splitlines()

    def test_valid_id_reference_no_problem(self):
        mappings = {"bodyPart": _mapping("bodyPart", "0")}
        nodes = _nodes(("0", "bodyPart"))
        lines = self._lines('<component node="bodyPart"/>')
        assert check_references(lines, mappings, nodes) == []

    def test_reference_to_missing_id(self):
        mappings: dict[str, I3dMapping] = {}
        nodes: dict[str, I3dNode] = {}
        lines = self._lines('<component node="missing"/>')
        problems = check_references(lines, mappings, nodes)
        assert len(problems) == 1
        assert problems[0].rule_id == "reference-to-non-existent-id"
        assert "missing" in problems[0].message

    def test_reference_to_valid_path(self):
        mappings: dict[str, I3dMapping] = {}
        nodes = _nodes(("0|1", "child"))
        lines = self._lines('<component node="0|1"/>')
        assert check_references(lines, mappings, nodes) == []

    def test_reference_to_invalid_path(self):
        mappings: dict[str, I3dMapping] = {}
        nodes: dict[str, I3dNode] = {}
        lines = self._lines('<component node="9|9|9"/>')
        problems = check_references(lines, mappings, nodes)
        assert len(problems) == 1
        assert problems[0].rule_id == "reference-to-non-existent-path"

    def test_i3d_mapping_definition_line_skipped(self):
        # The id="..." on the definition line must not trigger a false positive
        mappings: dict[str, I3dMapping] = {}
        nodes: dict[str, I3dNode] = {}
        lines = self._lines('<i3dMapping id="x" node="0"/>')
        assert check_references(lines, mappings, nodes) == []

    def test_multiple_ref_attrs_on_one_line(self):
        mappings: dict[str, I3dMapping] = {}
        nodes: dict[str, I3dNode] = {}
        lines = self._lines('<wheels node="missingA" linkNode="missingB"/>')
        problems = check_references(lines, mappings, nodes)
        rule_ids = {p.rule_id for p in problems}
        assert rule_ids == {"reference-to-non-existent-id"}
        assert len(problems) == 2

    def test_empty_ref_value_skipped(self):
        # node="" should not generate a problem
        mappings: dict[str, I3dMapping] = {}
        nodes: dict[str, I3dNode] = {}
        lines = self._lines('<component node=""/>')
        assert check_references(lines, mappings, nodes) == []

    def test_gt_path_reference_normalised(self):
        mappings: dict[str, I3dMapping] = {}
        nodes = _nodes(("0|1", "x"))
        lines = self._lines('<component node="0>1"/>')
        assert check_references(lines, mappings, nodes) == []


# ===========================================================================
# deduplicate_problems
# ===========================================================================

class TestDeduplicateProblems:
    def test_empty_list(self):
        assert deduplicate_problems([]) == []

    def test_unique_problems_preserved(self):
        problems = [
            Problem("r1", 1, "msg a"),
            Problem("r2", 2, "msg b"),
        ]
        assert len(deduplicate_problems(problems)) == 2

    def test_exact_duplicates_removed(self):
        p = Problem("r1", 5, "same message")
        assert len(deduplicate_problems([p, p, p])) == 1

    def test_same_line_different_message_kept(self):
        problems = [
            Problem("r1", 5, "msg a"),
            Problem("r2", 5, "msg b"),
        ]
        assert len(deduplicate_problems(problems)) == 2

    def test_sorted_by_line_then_message(self):
        problems = [
            Problem("r1", 10, "zzz"),
            Problem("r2", 1, "aaa"),
            Problem("r3", 10, "aaa"),
        ]
        result = deduplicate_problems(problems)
        assert result[0].line_number == 1
        assert result[1].line_number == 10
        assert result[1].message == "aaa"
        assert result[2].line_number == 10
        assert result[2].message == "zzz"


# ===========================================================================
# run_checks  (integration via real fixture files)
# ===========================================================================

class TestRunChecksWithRealFixtures:
    @pytest.fixture(autouse=True)
    def skip_if_no_fixtures(self):
        if not REAL_XML.exists() or not REAL_I3D.exists():
            pytest.skip("Fixture files not present")

    def test_returns_list_of_problems(self, capsys):
        problems = run_checks(REAL_XML, REAL_I3D)
        assert isinstance(problems, list)
        assert all(isinstance(p, Problem) for p in problems)

    def test_finds_expected_i3d_nodes(self, capsys):
        nodes = load_i3d_nodes(REAL_I3D)
        assert len(nodes) > 0

    def test_finds_expected_mappings(self):
        mappings = load_i3d_mappings(REAL_XML)
        assert len(mappings) > 0

    def test_no_invalid_rule_ids(self, capsys):
        known_rules = {
            "invalid-node-path",
            "duplicate-mapping-id",
            "duplicate-node-path",
            "unused-mapping-id",
            "unused-mapping-id-invalid-node",
            "unused-mapping-id-name-mismatch",
            "reference-to-non-existent-id",
            "reference-to-non-existent-path",
        }
        problems = run_checks(REAL_XML, REAL_I3D)
        for p in problems:
            assert p.rule_id in known_rules, f"Unknown rule_id: {p.rule_id}"

    def test_problems_have_valid_line_numbers(self, capsys):
        total_lines = len(REAL_XML.read_text(encoding="utf-8").splitlines())
        problems = run_checks(REAL_XML, REAL_I3D)
        for p in problems:
            assert 1 <= p.line_number <= total_lines, (
                f"Line {p.line_number} out of range for {p.rule_id}"
            )
