"""Impala Tokenizer — extends Hive, removes Hive-only tokens."""
from __future__ import annotations

from sqlglot import tokens
from sqlglot.dialects.hive import Hive
from sqlglot.tokens import TokenType


# Multi-word keyword phrases to REMOVE from Hive's keyword table
# (keys that exist in Hive.Tokenizer.KEYWORDS but must not apply to Impala)
_HIVE_ONLY_KEYWORDS: frozenset[str] = frozenset(
    [
        # Hive-specific commands
        "ADD ARCHIVE",
        "ADD ARCHIVES",
        "ADD FILE",
        "ADD FILES",
        "ADD JAR",
        "ADD JARS",
        "MSCK REPAIR",
        # Hive time-travel syntax — Impala uses FOR SYSTEM_TIME/VERSION AS OF
        "TIMESTAMP AS OF",
        "VERSION AS OF",
    ]
)

# Additional multi-word keyword phrases to ADD for Impala
_IMPALA_KEYWORDS: dict[str, TokenType] = {
    # Impala time-travel (FOR SYSTEM_TIME AS OF / FOR SYSTEM_VERSION AS OF)
    # These are parsed as multi-token sequences in the Parser layer; we map
    # the leading phrase to a TIMESTAMP_SNAPSHOT / VERSION_SNAPSHOT token so
    # the base _parse_version() method can be overridden cleanly.
    "FOR SYSTEM_TIME AS OF": TokenType.TIMESTAMP_SNAPSHOT,
    "FOR SYSTEM_VERSION AS OF": TokenType.VERSION_SNAPSHOT,
    # UPSERT has the same grammar as INSERT in Impala
    "UPSERT": TokenType.INSERT,
}


class ImpalaTokenizer(Hive.Tokenizer):
    """Impala SQL tokenizer.

    Differences from Hive:
    - No $ PARAMETER tokens
    - No numeric literal suffixes (1L, 1BD, etc.)
    - No ADD JAR/FILE/ARCHIVE or MSCK REPAIR keywords
    - FOR SYSTEM_TIME/VERSION AS OF replaces Hive's TIMESTAMP/VERSION AS OF
    """

    # Remove Hive's $ parameter single-token mapping
    SINGLE_TOKENS = {
        k: v
        for k, v in Hive.Tokenizer.SINGLE_TOKENS.items()
        if v != TokenType.PARAMETER
    }

    # No Hive numeric suffixes
    NUMERIC_LITERALS: dict[str, str] = {}

    KEYWORDS = {
        **{k: v for k, v in Hive.Tokenizer.KEYWORDS.items() if k not in _HIVE_ONLY_KEYWORDS},
        **_IMPALA_KEYWORDS,
    }
