"""kNN SQL must not use :bind::cast — asyncpg leaves it as a syntax error."""

from search.recipe_search_service import build_knn_select_sql


def test_knn_sql_omits_null_filters() -> None:
    sql, params = build_knn_select_sql(
        query_vec="[0.1,0.2]",
        user_id="f2ec8893-5d96-4b8c-8ecd-3c3ea70dac34",
        diet_type="pescatarian",
        cooking_type=None,
        recipe_type=None,
        prep_method=None,
        limit_n=90,
        offset_n=0,
    )
    assert ":diet_type::" not in sql
    assert ":cooking_type::" not in sql
    assert "CAST(:diet_type AS text)" not in sql
    assert "CAST(rdc.diet_type AS text) = :diet_type" in sql
    assert "cooking_type" not in params
    assert params["diet_type"] == "pescatarian"
    assert params["limit_n"] == 90


def test_knn_sql_includes_optional_filters_when_set() -> None:
    sql, params = build_knn_select_sql(
        query_vec="[0.0]",
        user_id="f2ec8893-5d96-4b8c-8ecd-3c3ea70dac34",
        diet_type="vegan",
        cooking_type="raw_80_cooked_20",
        recipe_type="meal",
        prep_method="raw",
        limit_n=30,
        offset_n=0,
    )
    assert "CAST(r.cooking_type AS text) = :cooking_type" in sql
    assert params["cooking_type"] == "raw_80_cooked_20"
    assert params["recipe_type"] == "meal"
    assert params["prep_method"] == "raw"
