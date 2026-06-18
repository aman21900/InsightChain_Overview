# Importing requirements from database & singletons
from database import DatabaseManager
from singletons import _vs

def initialize():
    print("[STARTUP] Initializing database...")
    DatabaseManager.initialize_database()

    print("\n[STARTUP] Initializing vectorstore...")
    if not _vs.load_existing():
        print("[STARTUP] No existing index found — building from scratch (this may take a few minutes)...")
        _vs.build_index()
    else:
        print("[STARTUP] Existing index loaded. To rebuild, call _vs.build_index() manually.")

    print("\n[STARTUP] Schema context preview:")
    print(DatabaseManager.build_schema_context())
