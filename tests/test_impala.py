import sqlglot


def test_impala_dialect_is_registered():
    assert sqlglot.Dialect.get("impala") is not None


def test_basic_select_roundtrip():
    sql = "SELECT * FROM users WHERE id = 1"
    result = sqlglot.transpile(sql, read="impala", write="impala")[0]
    assert result == sql
