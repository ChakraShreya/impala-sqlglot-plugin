"""Impala Generator — extends Hive, removes Hive-only generation transforms."""
from __future__ import annotations

from sqlglot import exp
from sqlglot.dialects.hive import Hive
from sqlglot.generators.hive import HiveGenerator


class ImpalaGenerator(HiveGenerator):
    """Impala SQL generator.

    Phase 0 changes:
    - Remove exp.ILike → LIKE rewrite (Impala supports ILIKE natively)
    - Remove exp.Unnest → EXPLODE rewrite (Impala uses UNNEST())
    - Enable JOIN/QUERY/TABLE hints

    Later phases will add UPSERT, OPTIMIZE, plan hint emission, etc.
    """

    # Impala natively supports plan hints
    JOIN_HINTS: bool = True
    TABLE_HINTS: bool = True
    QUERY_HINTS: bool = True

    TRANSFORMS = {
        **{
            k: v
            for k, v in HiveGenerator.TRANSFORMS.items()
            # Block Hive transforms that are wrong for Impala
            if k
            not in (
                exp.ILike,      # Hive rewrites ILIKE → LIKE; Impala supports ILIKE
                exp.Unnest,     # Hive rewrites UNNEST → EXPLODE; Impala uses UNNEST()
            )
        },
    }
