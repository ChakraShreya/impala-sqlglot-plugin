"""Shared pytest configuration and fixture helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "parser_test"

# Ensure the tests directory is on sys.path so test modules can import conftest
import sys as _sys
_tests_dir = str(Path(__file__).parent)
if _tests_dir not in _sys.path:
    _sys.path.insert(0, _tests_dir)


@dataclass
class ParserCase:
    sql: str
    expect: str        # "ok" or "error"
    source: str        # e.g. "ParserTest.TestSelect"
    phase: int
    dynamic: bool = False


def load_fixtures(phase: int | None = None, method: str | None = None) -> List[ParserCase]:
    """Load cases from fixture JSON files, optionally filtered by phase or method."""
    cases: List[ParserCase] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        if phase is not None and data.get("phase") != phase:
            continue
        if method is not None and not data["source"].endswith(f".{method}"):
            continue
        for c in data.get("cases", []):
            cases.append(
                ParserCase(
                    sql=c["sql"],
                    expect=c["expect"],
                    source=data["source"],
                    phase=data["phase"],
                    dynamic=c.get("dynamic", False),
                )
            )
    return cases


def case_id(case: ParserCase) -> str:
    """Stable pytest ID for a case."""
    short = case.sql[:60].replace("\n", " ")
    return f"{case.source}::{case.expect}::{short}"
