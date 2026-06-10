"""Impala Parser — extends Hive, blocks Hive-only constructs."""
from __future__ import annotations

import typing as t

from sqlglot import exp
from sqlglot.dialects.hive import Hive
from sqlglot.tokens import TokenType


class ImpalaParser(Hive.Parser):
    """Impala SQL parser.

    Phase 0 changes:
    - Remove TRANSFORM … USING from NO_PAREN_FUNCTION_PARSERS
    - Revert _parse_partition_and_order to base (no DISTRIBUTE BY / CLUSTER BY)
    - Block $-parameter parsing (handled by tokenizer removing the $ token)

    Later phases will add:
    - FOR SYSTEM_TIME/VERSION AS OF time-travel
    - TABLESAMPLE SYSTEM(n) REPEATABLE(s)
    - Plan hints (/* +hint */, [hint], straight_join)
    - UPSERT, OPTIMIZE, COMPUTE STATS, INVALIDATE METADATA, etc.
    """

    # Remove Hive-only TRANSFORM … USING parser
    NO_PAREN_FUNCTION_PARSERS: dict[str, t.Callable] = {
        k: v
        for k, v in Hive.Parser.NO_PAREN_FUNCTION_PARSERS.items()
        if k != "TRANSFORM"
    }

    def _parse_partition_and_order(
        self,
    ) -> tuple[list[exp.Expression], t.Optional[exp.Expression]]:
        """Impala has no DISTRIBUTE BY / CLUSTER BY / SORT BY in SELECT.
        Revert to the base parser's PARTITION BY + ORDER BY only.
        """
        from sqlglot import parser as _parser
        return _parser.Parser._parse_partition_and_order(self)
