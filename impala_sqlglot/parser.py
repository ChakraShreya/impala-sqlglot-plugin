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

    Phase 3+ changes:
    - COMMENT ON ... IS NULL support
    - DROP FUNCTION with variadic signatures (INT...)
    """

    # Remove Hive-only TRANSFORM … USING parser
    NO_PAREN_FUNCTION_PARSERS: dict[str, t.Callable] = {
        k: v
        for k, v in Hive.Parser.NO_PAREN_FUNCTION_PARSERS.items()
        if k != "TRANSFORM"
    }

    CONSTRAINT_PARSERS = {
        **Hive.Parser.CONSTRAINT_PARSERS,
        "NON UNIQUE PRIMARY KEY": lambda self: self._parse_primary_key(),
    }

    STATEMENT_PARSERS = {
        **Hive.Parser.STATEMENT_PARSERS,
        TokenType.COLON: lambda self: self._parse_impala_admin_fn(),
        TokenType.REFRESH: lambda self: self._parse_impala_refresh(),
    }

    def _parse_version(self) -> exp.Version | None:
        if self._match_text_seq("FOR", "SYSTEM_TIME", "AS", "OF"):
            kind = "TIMESTAMP"
        elif self._match_text_seq("FOR", "SYSTEM_VERSION", "AS", "OF"):
            kind = "VERSION"
        else:
            return super()._parse_version()

        expression = self._parse_bitwise()
        if expression is None:
            self.raise_error("Expected time-travel value after AS OF")

        return self.expression(
            exp.Version(this=kind, expression=expression, kind="AS OF")
        )

    def _parse_partition_and_order(
        self,
    ) -> tuple[list[exp.Expression], t.Optional[exp.Expression]]:
        """Impala has no DISTRIBUTE BY / CLUSTER BY / SORT BY in SELECT.
        Revert to the base parser's PARTITION BY + ORDER BY only.
        """
        from sqlglot import parser as _parser
        return _parser.Parser._parse_partition_and_order(self)

    def _parse_impala_admin_fn(self) -> exp.Command:
        """Parse :function_name(...) admin function calls."""
        start = self._prev
        while self._curr:
            self._advance()
        text = self._find_sql(start, self._prev)
        return exp.Command(this=text[:1], expression=text[1:])

    def _parse_impala_refresh(self) -> exp.Refresh | exp.Command:
        """Override REFRESH to handle PARTITION clause and FUNCTIONS (Impala-specific)."""
        start = self._prev
        while self._curr:
            self._advance()
        text = self._find_sql(start, self._prev)
        return exp.Command(this="REFRESH", expression=text[len("REFRESH"):])


    def _parse_comment(self, allow_exists: bool = True) -> exp.Expression:
        """Override to support COMMENT ON ... IS NULL (clearing a comment)."""
        start = self._prev
        exists = self._parse_exists() if allow_exists else None

        self._match(TokenType.ON)

        materialized = self._match_text_seq("MATERIALIZED")
        kind = self._match_set(self.CREATABLES) and self._prev
        if not kind:
            return self._parse_as_command(start)

        if kind.token_type in (TokenType.FUNCTION, TokenType.PROCEDURE):
            this = self._parse_user_defined_function(kind=kind.token_type)
        elif kind.token_type == TokenType.TABLE:
            this = self._parse_table(alias_tokens=self.COMMENT_TABLE_ALIAS_TOKENS)
        elif kind.token_type == TokenType.COLUMN:
            this = self._parse_column()
        else:
            this = self._parse_table_parts(schema=True)

        self._match(TokenType.IS)

        if self._match(TokenType.NULL):
            expression: t.Optional[exp.Expression] = exp.Null()
        else:
            expression = self._parse_string()

        return self.expression(
            exp.Comment(
                this=this,
                kind=kind.text,
                expression=expression,
                exists=exists,
                materialized=materialized,
            )
        )
