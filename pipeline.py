# Importing requirements from config, database, singletons, models & executor.
from config import CONCURRENCY_CAP, MAX_SUBQUESTIONS
from config import List, Dict, Tuple
from config import ThreadPoolExecutor, as_completed
from database import DatabaseManager
import singletons
from models import SubQuestions
from executor import execute_sub_question



def perform_vectorstore_schema_retrieval(user_query: str, log: List[str]) -> Tuple[str, List[str]]:
    """Performs vectorstore schema retrieval for decomposer."""
    log.append("[1] Retrieving relevant schema context from vectorstore...")
    try:
        schema_ctx = singletons._vs.retrieve_schema_context(user_query, top_k=5)
        log.append(f"    Schema context retrieved ({len(schema_ctx)} chars).")
    except Exception as e:
        schema_ctx = DatabaseManager.build_schema_context()
        log.append(f"    Vectorstore retrieval failed ({e}), using full schema fallback.")
    finally:
        return schema_ctx, log



def perform_query_decomposition(user_query: str, schema_ctx: str, log: List[str]) -> Tuple[List[SubQuestions], List[str]]:
    """Performing user query decomposition using schema context"""

    log.append("[2] Decomposing query into sub-questions...")

    sub_questions: List[SubQuestions] = []

    try:
        decomp_out  = singletons._decomposer.invoke({
            "user_query":     user_query,
            "schema_context": schema_ctx,
            "max_questions":  MAX_SUBQUESTIONS
        })

        raw_questions = decomp_out.get("questions", [])

        for q in raw_questions[:MAX_SUBQUESTIONS]:
            if isinstance(q, dict):
                sub_questions.append(SubQuestions(
                    question=q.get("question", "").strip(),
                    chart_type=q.get("chart_type", "").strip().lower(),
                    reason=q.get("reason", "").strip().lower(),
                    route=q.get("route", "SQL").strip()
                ))
            elif isinstance(q, SubQuestions):
                sub_questions.append(q)

        log.append(f"    {len(sub_questions)} sub-question(s) generated:")
        for i, sq in enumerate(sub_questions, start=1):
            log.append(f"      {i}.[{sq.route.upper()}] [{sq.chart_type.upper()}] {sq.question}")

    except Exception as e:
        log.append(f"    Decomposition failed ({e}), using original query as fallback.")


    # Fallback if decomposition produced nothing.
    if not sub_questions:
        sub_questions = [SubQuestions(
            question=user_query,
            chart_type="",
            reason="fallback — decomposition failed",
            route="SQL"
        )]
        log.append("    Fallback: using original query as single sub-question.")
        return sub_questions, log
    else:
        return sub_questions, log



def perform_parallel_subquestion_execution(sub_questions: List[SubQuestions], log: List[str]) -> Tuple[List[Dict], List[str]] :
    """Processing the subquestions parallely x at a time, where x is CONCURRENCY_CAP"""

    log.append(f"[3] Executing {len(sub_questions)} sub-question(s) (concurrency cap = {CONCURRENCY_CAP})...")
    results: List[Dict] = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY_CAP) as executor:
        futures = {executor.submit(execute_sub_question, sq): sq for sq in sub_questions}
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
                status = "✓" if not res.get("error") else "✗"
                log.append(
                    f"    {status} [{res['route']}] [{res.get('chart_type', '?').upper()}] "
                    f"{res['sub_question'][:70]}"
                )
            except Exception as e:
                log.append(f"    ✗ Sub-question execution exception: {e}")

    return results, log

def perform_sufficiency_check(results: List[Dict], user_query: str, log: List[str]) -> Tuple[bool, str, List[str]]:
    """Running the sufficiency check on the results."""

    log.append("[4] Running sufficiency check...")
    sufficient = True
    missing = ""
    try:
        results_summary = "\n\n".join(
            f"Q: {r['sub_question']}\n"
            f"Chart type: {r.get('chart_type', '?')}\n"
            f"Result rows: {len(r['df'])}\n"
            f"Insight: {r['insight'][:200]}"
            for r in results if not r.get("error")
        )
        suff_out = singletons._sufficiency.invoke({
            "user_query":      user_query,
            "results_summary": results_summary
        })
        sufficient = suff_out.get("sufficient", True)
        missing    = suff_out.get("missing", "")
        log.append(
            f"    Sufficient: {sufficient}"
            + (f" | Missing: {missing}" if not sufficient else "")
        )
    except Exception as e:
        sufficient = True
        missing    = ""
        log.append(f"    Sufficiency check failed ({e}), proceeding.")

    return sufficient, missing, log



def ask_followup_question(schema_ctx: str, missing: str, results: List[Dict], log: List[str]) -> Tuple[List[Dict], List[str]]:

    """Asking followup question"""

    log.append(f"[4b] Generating 1 follow-up sub-question for: '{missing[:80]}'")
    try:
        followup_decomp = singletons._decomposer.invoke({
            "user_query":     missing,
            "schema_context": schema_ctx,
            "max_questions":  1
        })
        followup_raw = followup_decomp.get("questions", [])[:1]

        for q in followup_raw:
            if isinstance(q, dict):
                fq = SubQuestions(
                    question=q.get("question", missing).strip(),
                    chart_type=q.get("chart_type", "bar").strip().lower(),
                    reason="sufficiency follow-up",
                    route=q.get("route", "SQL").strip().upper()
                )
            elif isinstance(q, SubQuestions):
                fq = q
            else:
                continue

            log.append(f"    Follow-up: [{fq.route}] [{fq.chart_type.upper()}] {fq.question}")
            fres = execute_sub_question(fq)
            results.append(fres)
            status = "✓" if not fres.get("error") else "✗"
            log.append(
                f"    {status} Follow-up executed — "
                f"[{fres['route']}] [{fres.get('chart_type','?').upper()}]"
            )
    except Exception as e:
        log.append(f"    Follow-up failed ({e}), proceeding with existing results.")
    finally:
        return results, log



def perform_narrative_generation(user_query: str, results: List[Dict] ,log: List[str]) -> Tuple[str,List[str]]:

    log.append("[5] Generating executive narrative...")
    try:
        def _summarise(r: Dict) -> str:
            df = r.get("df")
            if df is None or df.empty:
                data_preview = "No data"
            else:
                # Cap at 5 rows and 500 chars to stay well within TPM limits
                preview = df.head(5).to_string(index=False)
                if len(preview) > 500:
                    preview = preview[:500] + "..."
                data_preview = f"{len(df)} rows total. Sample:\n{preview}"
            insight = (r.get("insight") or "")[:400]
            return (
                f"Question: {r['sub_question']}\n"
                f"Chart Type: {r.get('chart_type', '?')}\n"
                f"Route: {r['route']}\n"
                f"Data: {data_preview}\n"
                f"Insight: {insight}"
            )

        all_results_str = "\n\n".join(_summarise(r) for r in results)
        narrative = singletons._reducer.invoke({
            "user_query":  user_query,
            "all_results": all_results_str
        })
        log.append("    Narrative generated.")
    except Exception as e:
        narrative = "Narrative synthesis failed. See individual panel insights above."
        log.append(f"    Reducer failed: {e}")

    return narrative, log

print("[PIPELINE] Pipelines defined.")