# Importing requirements from vectorstore.py & chains.py
from chains import (build_decomposer_chain, build_sql_chain, build_semantic_chain, build_sufficiency_chain,
                    build_reducer_chain, build_sql_repair_chain, build_mini_insight_chain)
from vectorstore import UnifiedVectorStore


# Defining the global state.

# Singletons — built once per session
_vs            = UnifiedVectorStore()
_decomposer    = None
_sql_chain     = None
_sql_repair    = None
_semantic      = None
_sufficiency   = None
_reducer       = None
_mini_insight  = None

def ensure_chains():
    global _decomposer, _sql_chain, _semantic, _sufficiency, _reducer, _sql_repair, _mini_insight
    print(f"[ENSURE_CHAINS] Called. _decomposer={_decomposer}, _sql_chain={_sql_chain}")  # add this
    if any(c is None for c in [_decomposer, _sql_chain, _semantic, _sufficiency, _reducer, _sql_repair, _mini_insight]):
        print("[INIT] Building LangChain chains...")
        try:
            _decomposer   = build_decomposer_chain()
            print("[INIT] Decomposer built.")
            _sql_chain    = build_sql_chain()
            print("[INIT] SQL chain built.")
            _sql_repair   = build_sql_repair_chain()
            print("[INIT] SQL repair chain built.")
            _mini_insight = build_mini_insight_chain()
            print("[INIT] Mini-Insight chain built.]")
            _semantic     = build_semantic_chain()
            print("[INIT] Semantic chain built.")
            _sufficiency  = build_sufficiency_chain()
            print("[INIT] Sufficiency chain built.")
            _reducer      = build_reducer_chain()
            print("[INIT] All chains ready.")
        except Exception as e:
            print(f"[INIT ERROR] Chain building failed at: {e}")
            import traceback
            traceback.print_exc()
            raise

print("[STATE] Global state initialized.")