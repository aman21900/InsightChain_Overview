# Importing requirements from config.py, render_dashboard.py, pipeline.py and singletons.py

from config import MAX_FOLLOW_UP_QUESTIONS
from config import List, Tuple, Dict, Any
from render_dashboard import render_dashboard
from pipeline import (perform_sufficiency_check, perform_parallel_subquestion_execution,
                      perform_narrative_generation, perform_query_decomposition,
                      perform_vectorstore_schema_retrieval, ask_followup_question)
from singletons import ensure_chains


def process_query(user_query: str) -> Tuple[str, List[Any], str]:
    try:
        return process_query_impl(user_query)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        return f"FATAL ERROR:\n{tb}", [], f"<p style='color:red'><pre>{tb}</pre></p>"


def process_query_impl(user_query: str) -> Tuple[str, List[Any], str]:
    """
    Main orchestrator. Called by Gradio on every submit.
    Returns: (pipeline_log: str, figures: List[go.Figure], dashboard_html: str)
    """
    if not user_query or not user_query.strip():
        return "Please enter a question.", [], "<p>No query entered.</p>"

    sufficient = False
    ensure_chains()
    log: List[str] = []

    schema_ctx, log = perform_vectorstore_schema_retrieval(user_query, log)
    sub_questions, log = perform_query_decomposition(user_query, schema_ctx, log)
    results, log = perform_parallel_subquestion_execution(sub_questions, log)

    if not results:
        return "\n".join(log), [], "<p>⚠ All sub-questions failed. Check the pipeline log.</p>"

    asked_questions = 0
    while not sufficient and (asked_questions < MAX_FOLLOW_UP_QUESTIONS):
        sufficient, missing, log = perform_sufficiency_check(results, user_query, log)
        if not sufficient and missing:
            results, log = ask_followup_question(schema_ctx, missing, results, log)
        asked_questions += 1

    narrative, log = perform_narrative_generation(user_query, results, log)

    log.append("[6] Rendering dashboard...")

    # Extract figures for gr.Plot — one per result that has a valid figure
    figures = [r["fig"] for r in results if r.get("fig") is not None]

    dashboard_html = render_dashboard(results, narrative, user_query)
    log.append(f"    Done — {len(results)} panel(s), {len(figures)} chart(s).")

    return "\n".join(log), figures, dashboard_html


print("[ORCHESTRATOR] process_query defined.")