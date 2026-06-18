# Importing requirements from config.py
from config import SPREADSHEETS_DIR, DB_PATH, SCHEMA_CACHE_TTL
from config import Dict, Any, List
from config import Path
from config import pd, sqlite3, time



class DatabaseManager:
    """
    Handles SQLite ingestion from CSVs, live schema introspection via PRAGMA,
    and a TTL-cached schema context string.
    """
    _schema_cache: Dict[str, Any] = {"data": None, "timestamp": 0}

    @staticmethod
    def initialize_database() -> None:
        """Load all CSVs from data/ into SQLite tables."""
        csv_files = list(Path(SPREADSHEETS_DIR).glob("*.csv"))
        if not csv_files:
            print(f"[DB INIT] No CSV files found in '{SPREADSHEETS_DIR}'")
            return

        with sqlite3.connect(DB_PATH) as conn:
            for csv_path in csv_files:
                table_name = csv_path.stem.lower().replace(" ", "_").replace("-", "_")
                df = pd.read_csv(csv_path)
                df.to_sql(table_name, conn, if_exists="replace", index=False)
                print(f"[DB INIT] '{table_name}' loaded — {len(df)} rows × {len(df.columns)} cols")
        print(f"[DB INIT] Database ready at: {DB_PATH}")



    @staticmethod
    def get_all_tables() -> List[str]:
        """Return list of all table names in the database."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]



    @staticmethod
    def get_table_columns(table_name: str) -> List[Dict]:
        """Use PRAGMA to get column info directly from the live DB — never from CSV headers."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        # Each row: (cid, name, type, notnull, dflt_value, pk)
        return [{"name": r[1], "type": r[2]} for r in rows]



    @classmethod
    def build_schema_context(cls) -> str:
        """
        Build a schema context string from PRAGMA — cached with TTL.
        This is the only place schema context is generated; never from CSV headers.
        """
        now = time.time()
        if cls._schema_cache["data"] and (now - cls._schema_cache["timestamp"]) < SCHEMA_CACHE_TTL:
            return cls._schema_cache["data"]

        tables = cls.get_all_tables()
        lines = ["Available database tables and their columns:\n"]
        for table in tables:
            cols = cls.get_table_columns(table)
            col_str = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
            lines.append(f"  Table '{table}': [{col_str}]")
        result = "\n".join(lines)

        cls._schema_cache["data"] = result
        cls._schema_cache["timestamp"] = now
        return result



    @staticmethod
    def execute_query(sql: str) -> pd.DataFrame:
        """Execute a validated SELECT query and return results as a DataFrame."""
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query(sql, conn)



    @staticmethod
    def sample_table(table_name: str, n: int = 200) -> pd.DataFrame:
        """Sample n rows randomly for vectorstore data indexing."""
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query(f"SELECT DISTINCT * FROM {table_name} ORDER BY RANDOM() LIMIT {n}", conn)



print("[DB] DatabaseManager defined.")