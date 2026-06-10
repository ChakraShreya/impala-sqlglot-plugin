#!/usr/bin/env python3
"""
Extract ParserTest.java test cases into per-method JSON fixture files.

Usage:
    python tools/extract_parser_tests.py --input <path/to/ParserTest.java> \
                                         --out-dir tests/fixtures/parser_test \
                                         --matrix tests/coverage_matrix.yaml

The extractor:
  - Walks @Test public void TestXxx() blocks
  - Captures static ParsesOk("...") and ParserError("...") literals
  - Maps each method to a phase using PHASE_MAP
  - Emits tests/fixtures/parser_test/<method>.json (one per test method)
  - Emits tests/coverage_matrix.yaml with phase/status metadata
  - Flags dynamic cases (String.format, loops) for manual curation
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path

try:
    import yaml  # optional PyYAML
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------------
# Phase assignment map  (ParserTest method → phase number)
# ---------------------------------------------------------------------------
PHASE_MAP: dict[str, int] = {
    # Phase 0 — Foundation / tokenizer
    "TestUnreservedKeywords": 0,
    "TestIdentQuoting": 0,
    "TestIdentifier": 0,
    "TestLineBreakEnd": 0,
    "TestSemiColon": 0,
    # Phase 1 — Expressions & literals
    "TestNoFromClause": 1,
    "TestSelect": 1,
    "TestAlias": 1,
    "TestStar": 1,
    "TestLiteralExprs": 1,
    "TestNumericLiteralMinMaxValues": 1,
    "TestArithmeticExprs": 1,
    "TestFactorialPrecedenceAssociativity": 1,
    "TestTimestampArithmeticExprs": 1,
    "TestCastExprs": 1,
    "TestCaseExprs": 1,
    "TestConditionalExprs": 1,
    "TestFunctionCallExprs": 1,
    "TestSlotRef": 1,
    "TestPredicates": 1,
    "TestCompoundPredicates": 1,
    "TestBetweenPredicate": 1,
    "TestInPredicate": 1,
    "TestAggregateExprs": 1,
    "TestAnalyticExprs": 1,
    "TestMultilineComment": 1,
    "TestSinglelineComment": 1,
    # Phase 2 — Query shape
    "TestFromClause": 2,
    "TestWhereClause": 2,
    "TestHaving": 2,
    "TestGroupBy": 2,
    "TestOrderBy": 2,
    "TestLimit": 2,
    "TestOffset": 2,
    "TestSetOperations": 2,
    "TestValuesStmt": 2,
    "TestWithClause": 2,
    "TestTimeTravel": 2,
    "TestTableSampleClause": 2,
    "TestPlanHints": 2,
    "TestSubqueries": 2,
    "TestRollup": 2,
    "TestCube": 2,
    "TestGroupingSets": 2,
    "TestGroupingKeyword": 2,
    # Phase 3 — DML
    "TestInsert": 3,
    "TestUpsert": 3,
    "TestUpdate": 3,
    "TestKuduUpdate": 3,
    "TestDelete": 3,
    "TestMerge": 3,
    "TestOptimize": 3,
    # Phase 4 — DDL / types
    "TestTypes": 4,
    "TestCreateTable": 4,
    "TestCreateTableAsSelect": 4,
    "TestCreateView": 4,
    "TestAlterView": 4,
    "TestCreateDatabase": 4,
    "TestAlterDatabaseSetOwner": 4,
    "TestAlterDatabaseSetDbProperties": 4,
    "TestAlterTableAddColumn": 4,
    "TestAlterTableAddReplaceColumns": 4,
    "TestAlterTableAddPartition": 4,
    "TestAlterTableSetPartitionSpec": 4,
    "TestAlterTableDropColumn": 4,
    "TestAlterTableDropPartition": 4,
    "TestAlterTableChangeColumn": 4,
    "TestAlterTableSet": 4,
    "TestAlterTableSortBy": 4,
    "TestAlterTableZSortBy": 4,
    "TestAlterTableOrViewRename": 4,
    "TestAlterTableRecoverPartitions": 4,
    "TestAlterTableAlterColumn": 4,
    "TestAlterTableOrViewSetOwner": 4,
    "TestCreateFunction": 4,
    "TestCreateAggregate": 4,
    "TestVariadicCreateFunctions": 4,
    "TestCreateDataSource": 4,
    "TestDropDataSource": 4,
    "TestDrop": 4,
    "TestTruncateTable": 4,
    "TestLoadData": 4,
    "TestCreateDropRole": 4,
    "TestGrantRevokeRole": 4,
    "TestGrantRevokePrivilege": 4,
    "TestCommentOn": 4,
    # Phase 5 — SHOW / admin
    "TestUse": 5,
    "TestShow": 5,
    "TestShowCreateTable": 5,
    "TestShowCreateFunction": 5,
    "TestShowRoles": 5,
    "TestShowCurrentGroups": 5,
    "TestShowGrantPrincipal": 5,
    "TestDescribeDb": 5,
    "TestDescribeTable": 5,
    "TestDescribeHistory": 5,
    "TestExplain": 5,
    "TestSet": 5,
    "TestResetMetadata": 5,
    "TestComputeStats": 5,
    "TestComputeIncrementalStats": 5,
    "TestComputeDropStats": 5,
    "TestAdminFns": 5,
    "TestCopyTestCase": 5,
    "TestGetErrorMsg": 5,  # skip / optional
}

# CUP grammar rules for each method (documentation metadata only)
CUP_RULES: dict[str, list[str]] = {
    "TestSelect": ["select_stmt", "select_list"],
    "TestStar": ["select_list_item", "star_expr"],
    "TestAlias": ["alias_clause"],
    "TestNoFromClause": ["select_stmt"],
    "TestFromClause": ["from_clause", "join_operator"],
    "TestWhereClause": ["where_clause"],
    "TestGroupBy": ["group_by_clause"],
    "TestOrderBy": ["order_by_elements"],
    "TestHaving": ["having_clause"],
    "TestLimit": ["opt_limit_clause"],
    "TestOffset": ["opt_offset_clause"],
    "TestSetOperations": ["set_operand_list", "set_op"],
    "TestValuesStmt": ["values_stmt"],
    "TestWithClause": ["opt_with_clause"],
    "TestTimeTravel": ["opt_asof"],
    "TestTableSampleClause": ["opt_tablesample"],
    "TestPlanHints": ["opt_plan_hints", "plan_hint"],
    "TestPredicates": ["comparison_predicate", "like_predicate"],
    "TestCompoundPredicates": ["compound_predicate"],
    "TestBetweenPredicate": ["between_predicate"],
    "TestInPredicate": ["in_predicate"],
    "TestCastExprs": ["cast_expr", "cast_format_val"],
    "TestCaseExprs": ["case_expr"],
    "TestArithmeticExprs": ["arithmetic_expr"],
    "TestInsert": ["insert_stmt"],
    "TestUpsert": ["upsert_stmt"],
    "TestUpdate": ["update_stmt"],
    "TestDelete": ["delete_stmt"],
    "TestMerge": ["merge_stmt"],
    "TestOptimize": ["optimize_stmt"],
    "TestCreateTable": ["create_tbl_stmt"],
    "TestCreateTableAsSelect": ["create_tbl_as_select_stmt"],
    "TestCreateView": ["create_view_stmt"],
    "TestAlterView": ["alter_view_stmt"],
    "TestTypes": ["type_def"],
    "TestResetMetadata": ["reset_metadata_stmt"],
    "TestComputeStats": ["compute_stats_stmt"],
    "TestAdminFns": ["admin_fn_stmt"],
}

HIVE_ACTION: dict[str, str] = {
    "TestTimeTravel": "block",  # Hive TIMESTAMP AS OF is wrong
    "TestTableSampleClause": "override",
    "TestPlanHints": "add",
    "TestUpsert": "add",
    "TestOptimize": "add",
    "TestComputeStats": "add",
    "TestComputeIncrementalStats": "add",
    "TestAdminFns": "add",
    "TestResetMetadata": "add",
    "TestIdentQuoting": "inherit",
    "TestSelect": "inherit",
    "TestFromClause": "inherit",
}

# ---------------------------------------------------------------------------
# Regex patterns for extracting static string literals from Java
# ---------------------------------------------------------------------------

# Match ParsesOk("some sql") or ParsesOk('some sql')
_PARSES_OK_RE = re.compile(
    r'ParsesOk\(\s*"((?:[^"\\]|\\.)*)"\s*(?:,\s*[A-Za-z][^)]*?)?\)',
    re.DOTALL,
)
_PARSER_ERROR_RE = re.compile(
    r'ParserError\(\s*"((?:[^"\\]|\\.)*)"\s*(?:,\s*"(?:[^"\\]|\\.)*")?\s*\)',
    re.DOTALL,
)

# Detect dynamic cases — String.format( or for ( loops
_DYNAMIC_RE = re.compile(r'String\.format|for\s*\(|\.replace\(')


def _unescape_java(s: str) -> str:
    """Convert Java string escapes to Python string."""
    return (
        s.replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def extract_method_body(source: str, method_name: str) -> str | None:
    """Return the source text of the method body (between outer braces)."""
    pattern = re.compile(
        r'public\s+void\s+' + re.escape(method_name) + r'\s*\([^)]*\)\s*(?:throws\s+\S+\s*)?\{',
        re.MULTILINE,
    )
    m = pattern.search(source)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        c = source[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    return source[start : i - 1]


def extract_cases(body: str) -> tuple[list[dict], bool]:
    """
    Return (cases, has_dynamic) where cases is a list of
    {"sql": ..., "expect": "ok"|"error", "dynamic": False}.
    has_dynamic is True if String.format / loops are present.
    """
    cases: list[dict] = []
    has_dynamic = bool(_DYNAMIC_RE.search(body))

    for m in _PARSES_OK_RE.finditer(body):
        sql = _unescape_java(m.group(1)).strip()
        if sql:
            cases.append({"sql": sql, "expect": "ok", "dynamic": False})

    for m in _PARSER_ERROR_RE.finditer(body):
        sql = _unescape_java(m.group(1)).strip()
        if sql:
            cases.append({"sql": sql, "expect": "error", "dynamic": False})

    return cases, has_dynamic


def load_yaml_safely(text: str) -> dict:
    """Load YAML or fall back to empty dict."""
    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


def dump_yaml(obj: dict) -> str:
    try:
        return yaml.dump(obj, default_flow_style=False, allow_unicode=True, sort_keys=True)
    except Exception:
        # Fallback: simple manual serialization
        lines = []
        for k, v in sorted(obj.items()):
            lines.append(f"{k}:")
            for fk, fv in v.items():
                if isinstance(fv, list):
                    fv_str = "[" + ", ".join(str(x) for x in fv) + "]"
                    lines.append(f"  {fk}: {fv_str}")
                else:
                    lines.append(f"  {fk}: {fv}")
        return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Path to ParserTest.java (or the downloaded .md proxy)",
    )
    parser.add_argument(
        "--out-dir",
        default="tests/fixtures/parser_test",
        help="Output directory for per-method JSON files",
    )
    parser.add_argument(
        "--matrix",
        default="tests/coverage_matrix.yaml",
        help="Output path for coverage_matrix.yaml",
    )
    args = parser.parse_args()

    src_path = Path(args.input)
    out_dir = Path(args.out_dir)
    matrix_path = Path(args.matrix)

    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_path.parent.mkdir(parents=True, exist_ok=True)

    source = src_path.read_text(encoding="utf-8")

    # Collect all @Test method names from source
    test_names = re.findall(
        r'public\s+void\s+(Test[A-Za-z0-9_]+)\s*\(',
        source,
    )

    matrix: dict[str, dict] = {}
    total_static = 0
    total_dynamic = 0

    for name in test_names:
        phase = PHASE_MAP.get(name, 5)  # default unmapped → phase 5
        body = extract_method_body(source, name)
        if body is None:
            continue

        cases, has_dynamic = extract_cases(body)
        total_static += len(cases)
        if has_dynamic:
            total_dynamic += 1

        fixture = {
            "source": f"ParserTest.{name}",
            "phase": phase,
            "has_dynamic": has_dynamic,
            "cases": cases,
        }

        out_file = out_dir / f"{name}.json"
        out_file.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")

        matrix[name] = {
            "phase": phase,
            "cup_rules": CUP_RULES.get(name, []),
            "hive": HIVE_ACTION.get(name, "inherit"),
            "has_dynamic": has_dynamic,
            "static_cases": len(cases),
            "status": "not_started",
        }

    # Write coverage matrix YAML (no PyYAML dependency required — write manually)
    yaml_lines = ["# Auto-generated by tools/extract_parser_tests.py", "# Do NOT edit by hand — re-run the extractor to regenerate", ""]
    for method, meta in sorted(matrix.items()):
        phase = meta["phase"]
        cup = meta["cup_rules"]
        cup_str = "[" + ", ".join(cup) + "]" if cup else "[]"
        yaml_lines.append(f"{method}:")
        yaml_lines.append(f"  phase: {phase}")
        yaml_lines.append(f"  cup_rules: {cup_str}")
        yaml_lines.append(f"  hive: {meta['hive']}")
        yaml_lines.append(f"  has_dynamic: {str(meta['has_dynamic']).lower()}")
        yaml_lines.append(f"  static_cases: {meta['static_cases']}")
        yaml_lines.append(f"  status: not_started  # not_started | in_progress | parse_ok | roundtrip_ok")
        yaml_lines.append("")

    matrix_path.write_text("\n".join(yaml_lines), encoding="utf-8")

    print(f"Extracted {len(test_names)} test methods → {out_dir}")
    print(f"  Static cases captured: {total_static}")
    print(f"  Methods with dynamic cases: {total_dynamic}")
    print(f"  Coverage matrix: {matrix_path}")


if __name__ == "__main__":
    main()
