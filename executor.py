# Importing requirements from config, models, singletons, database, & guardrails
from typing import Optional, Tuple
from config import Dict
from config import pd
import singletons
from database import DatabaseManager
from guardrails import SQLGuardrailValidator, SafeChartExecutor
from models import SubQuestions


def _generate_mini_insight(df: Optional[pd.DataFrame], sub_question: str) -> Tuple[str, str]:
    # Mini Insight Generation for the resulting df
    if df is None:
        return None, f"No Table Received."
    if df.empty:
        return None, f"SQL query could not fetch data."
    else:
        try:
            mini_insight_raw = singletons._mini_insight.invoke({
                "retrieved_table_data": df,
                "sub_question": sub_question
            })
            print(f"[Mini Insight] {mini_insight_raw}")
            return mini_insight_raw, None
        except Exception as e:
            return None, f"Mini Insight generation failed: {e}"


def _validate_and_execute(sql_query: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Runs SQLGuardrailValidator then DatabaseManager.execute_query.
    Returns (df, error_message). error_message is "" on success.
    """
    is_valid, msg = SQLGuardrailValidator.validate(sql_query)
    if not is_valid:
        return None, f"Validation Failed: {msg}"
    try:
        df = DatabaseManager.execute_query(sql_query)
        return df, ""
    except Exception as e:
        return None, f"Execution Failed: {e}"


def execute_sub_question(sub_question: SubQuestions) -> Dict:
    """
    Run one sub-question through the full pipeline.
    Route is set by the decomposer — no separate LLM call needed.
    Returns a dict with keys: sub_question, route, chart_type, sql, df, fig, insight, error
    """
    result = {
        "sub_question": sub_question.question,
        "chart_type": sub_question.chart_type,
        "route": "SQL",
        "sql": "",
        "df": pd.DataFrame(),
        "fig": None,
        "insight": "",
        "error": ""
    }

    # Taking the route generated during the decomposition step.
    route = (sub_question.route or "SQL").strip().upper()
    if route not in ("SQL", "SEMANTIC"):
        route = "SQL"
    result["route"] = route
    print(f"  [ROUTE] '{sub_question.question[:60]}' → {route}")

    # ==========================================================================
    # PATH A — SQL TRACK
    # ==========================================================================
    if route == "SQL":
        column_hints  = singletons._vs.retrieve_column_hints(sub_question.question)
        schema_context = DatabaseManager.build_schema_context()

        # Generating the SQL + Chart Code + Insights
        try:
            gen = singletons._sql_chain.invoke({
                "sub_question":   sub_question.question,
                "chart_type": sub_question.chart_type,
                "schema_context": schema_context,
                "column_hints":   column_hints
            })
            print(f"[GEN RAW] {gen}")
            sql_query = gen.get("sql_query", "").strip()
            chart_code = gen.get("chart_code", "fig = None")
            result["sql"] = sql_query
        except Exception as e:
            result["error"] = f"SQL generation failed: {e}"
            return result

        # Empty sql_query means LLM determined question is unanswerable with schema
        if not sql_query:
            result["error"] = "Not answerable: the required data does not exist in the schema."
            return result

        # Validating Guardrails SQL
        # is_valid, msg = SQLGuardrailValidator.validate(sql_query)
        # if not is_valid:
        #     result["error"] = f"SQL validation failed: {msg}"
        #     return result

        # Validating Guardrails and Executing SQL (Integrating the repair chain.)
        df, sql_run_error = _validate_and_execute(sql_query)

        # Invoking repair chain if an error is found in SQL.
        if sql_run_error:
            print(f"  [SQL RETRY] Attempt 1 failed: {sql_run_error}")

            try:
                repair_gen = singletons._sql_repair.invoke({
                    "sub_question": sub_question.question,
                    "chart_type": sub_question.chart_type,
                    "schema_context": schema_context,
                    "column_hints": column_hints,
                    "previous_sql": sql_query,
                    "error_message": sql_run_error
                })
                print(f"[REPAIR GEN RAW] {repair_gen}")
                sql_query = repair_gen.get("sql_query", "").strip()
                chart_code = repair_gen.get("chart_code", "fig=None")
                result["sql"] = sql_query
            except Exception as e:
                result["error"] = f"SQL repair generation failed: {e}. Original error: {sql_run_error}"
                return result

            if not sql_query:
                result["error"] = (
                    f"Not answerable: repair attempt determined the required data "
                    f"does not exist in the schema. Original error: {sql_run_error}"
                )
                return result

            # Second retry for executing the SQL query
            df, sql_run_error = _validate_and_execute(sql_query)
            if sql_run_error:
                print(f"  [SQL RETRY] Attempt 2 (repair) also failed: {sql_run_error}")

        if sql_run_error:
            result["error"] = f"SQL failed after repair attempt: {sql_run_error}"
            return result

        result["df"] = df
        print(f"  [SQL] {len(df)} rows returned. Columns: {df.columns.tolist()}")

        # Generating mini insight for the resulting df
        mini_insight_raw, insight_error = _generate_mini_insight(df, sub_question.question)
        result["insight"] = mini_insight_raw
        result["error"] = insight_error

        # Chart Generation
        # Inject actual column names into the chart code as a comment header so the
        # LLM-generated references are easier to debug, and patch any obvious mismatches.

        actual_columns = df.columns.tolist()
        column_context = f"# Actual DataFrame Columns: {', '.join(actual_columns)}\n"
        chart_code_with_actual_columns = column_context + chart_code.strip()

        print(f"[CHART CODE] >>>{chart_code_with_actual_columns}<<<")
        print(f"[DF EMPTY] {df.empty}, shape={df.shape}")
        print(f"[PRE-RUN] repr: {repr(chart_code_with_actual_columns)}")

        result["fig"], chart_error = SafeChartExecutor.run(df, chart_code_with_actual_columns)

        if chart_error:
            print(f"Chart Error: {chart_error}")
            # Append the error message to the insights:
            result["_chart_error"] = chart_error

    # ==========================================================================
    # PATH B — SEMANTIC TRACK
    # ==========================================================================
    else:
        retrieved = singletons._vs.retrieve_semantic_context(sub_question.question, top_k=15)
        try:
            narrative = singletons._semantic.invoke({
                "sub_question":      sub_question.question,
                "retrieved_context": retrieved
            })
            result["df"]      = pd.DataFrame({"Semantic Answer": [narrative]})
            result["insight"] = narrative
            print(f"  [SEMANTIC] Answer generated.")
        except Exception as e:
            result["error"] = f"Semantic chain failed: {e}"

    return result

print("[EXECUTOR] SUB-QUESTION EXECUTOR: execute_sub_question defined.")