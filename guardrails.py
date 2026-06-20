# Importing requirements from config.py
from config import builtins
from config import Tuple, Optional
from config import pd, go, px, sqlparse, re


class SQLGuardrailValidator:
    """
    Blocks any SQL that is not a plain SELECT statement.
    Prevents prompt injection attacks like 'SELECT 1; DROP TABLE orders;'
    Prevents multiple SQL statements to be generated at the same time.
    """
    FORBIDDEN = [
        "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
        "TRUNCATE", "CREATE", "REPLACE", "ATTACH", "DETACH"
    ]

    @staticmethod
    def validate(sql: str) -> Tuple[bool, str]:
        if not sql or not sql.strip():
            return False, "SQL query is empty."

        normalized = sql.strip().upper()

        if not normalized.lstrip().startswith("SELECT"):
            return False, f"Rejected: must start with SELECT. Got: '{normalized[:50]}'"

        for kw in SQLGuardrailValidator.FORBIDDEN:
            if re.search(rf'\b{kw}\b', normalized):
                return False, f"Rejected: forbidden keyword '{kw}' detected."

        parsed = [s for s in sqlparse.parse(sql) if s.get_type() is not None]
        if len(parsed) > 1:
            return False, "Rejected: multiple SQL statements detected."

        return True, "Validation passed."

print("[VALIDATOR] SQLGuardrailValidator defined.")



_DANGEROUS_BUILTINS = {
    "open", "exec", "eval", "__import__", "compile", "input",
    "breakpoint", "memoryview", "globals", "locals", "vars",
    "setattr", "delattr", "__loader__", "exit", "quit"
}
SAFE_BUILTINS = {k: v for k, v in builtins.__dict__.items() if k not in _DANGEROUS_BUILTINS}

_DANGEROUS_PATTERNS = [
    r"\bopen\s*\(",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"__import__",
    r"import\s+os",
    r"import\s+sys",
    r"import\s+subprocess",
    r"import\s+shutil",
]

class SafeChartExecutor:
    """Executes LLM-generated Plotly chart code in a sandboxed exec() environment."""

    @staticmethod
    def run(df: pd.DataFrame, chart_code: str) -> Tuple[Optional[go.Figure], str]:
        if df is None or df.empty:
            return None, "DataFrame is empty. Chart Skipped."
        if not chart_code or chart_code.strip() in ("", "fig = None", "fig=None"):
            return None, ""

        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, chart_code, re.IGNORECASE):
                print(f"[PATTERN HIT] {pattern}")
                break
        else:
            print("[PATTERN] all clear")

        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, chart_code, re.IGNORECASE):
                msg = f"Blocked - dangerous pattern '{pattern}' detected."
                print(f"[CHART] Blocked — dangerous pattern: {pattern}")
                return None, msg

        scope = {
            "df": df, "px": px, "go": go, "pd": pd,
            "fig": None, "__builtins__": SAFE_BUILTINS
        }
        try:
            exec(chart_code, scope)
            print(f"[EXEC DONE] fig type={type(scope.get('fig'))}, fig={scope.get('fig')}")
            fig = scope.get("fig", None)
            if fig is not None and not isinstance(fig, go.Figure):
                msg = f"'fig is not a Plotly figure (got {type(fig).__name__}) - discarding."
                print(f"[CHART] {msg}")
                return None, msg
            return fig, ""
        except Exception as e:
            msg = f"[CHART] {type(e).__name__}: {e}"
            print(f"[CHART ERROR] {msg}")
            print(f"[CHART CODE DUMP]\n{chart_code}")
            return None, msg


print("[CHART] SafeChartExecutor defined.")