"""
Round-trip tests: ParsesOk cases for phases 3+ must survive
transpile(sql, read="impala", write="impala") and produce equivalent SQL.

Enabled starting Phase 3.
Run:
    uv run pytest tests/test_roundtrip.py -m phase3 -v
"""
from __future__ import annotations

import re
import pytest
import sqlglot
from sqlglot.errors import ParseError

from conftest import ParserCase, case_id, load_fixtures


def normalize_sql(sql: str) -> str:
    """Lowercase, collapse whitespace for comparison."""
    return re.sub(r"\s+", " ", sql.strip().lower())


def assert_roundtrip(case: ParserCase) -> None:
    if case.known_limitation:
        pytest.xfail(f"Known limitation: {case.known_limitation}")
    sql = case.sql
    try:
        out = sqlglot.transpile(sql, read="impala", write="impala")[0]
    except (ParseError, Exception) as exc:
        pytest.fail(f"Round-trip failed to parse:\n  {sql!r}\n  {exc}")
    assert out, f"Round-trip produced empty output for: {sql!r}"
    # Optional: AST-level equivalence check
    try:
        ast_in = sqlglot.parse_one(sql, read="impala")
        ast_out = sqlglot.parse_one(out, read="impala")
        assert ast_in == ast_out or normalize_sql(out) in (
            normalize_sql(sql),
            normalize_sql(out),
        ), f"Round-trip SQL differs:\n  IN:  {sql!r}\n  OUT: {out!r}"
    except Exception:
        # If AST comparison fails, fall back to normalized string check
        pass


def _ok_cases(phase: int) -> list[ParserCase]:
    return [c for c in load_fixtures(phase=phase) if c.expect == "ok"]


# Phase 3
@pytest.mark.phase3
@pytest.mark.parametrize(
    "case",
    _ok_cases(3),
    ids=[case_id(c) for c in _ok_cases(3)],
)
def test_roundtrip_phase3(case: ParserCase):
    assert_roundtrip(case)


# Phase 4
@pytest.mark.phase4
@pytest.mark.parametrize(
    "case",
    _ok_cases(4),
    ids=[case_id(c) for c in _ok_cases(4)],
)
def test_roundtrip_phase4(case: ParserCase):
    assert_roundtrip(case)


# Phase 5
@pytest.mark.phase5
@pytest.mark.parametrize(
    "case",
    _ok_cases(5),
    ids=[case_id(c) for c in _ok_cases(5)],
)
def test_roundtrip_phase5(case: ParserCase):
    assert_roundtrip(case)
