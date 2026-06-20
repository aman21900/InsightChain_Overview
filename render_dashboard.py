from config import List, Dict


def render_dashboard(results: List[Dict], narrative: str, user_query: str) -> str:
    """
    Renders tables + insights + narrative as HTML.
    Charts are handled separately via gr.Plot in ui.py.
    """
    panels_html = ""

    for r in results:
        if r.get("error"):
            panels_html += f"""
            <div class="panel error-panel">
              <div class="panel-title">{r['sub_question']}</div>
              <div class="error-msg">⚠ {r['error']}</div>
            </div>"""
            continue

        # DataFrame → HTML table
        table_html = ""
        if r.get("df") is not None and not r["df"].empty:
            table_html = r["df"].head(20).to_html(
                index=False,
                classes="data-table",
                border=0
            )

        # Insight bullets
        insight_html = ""
        if r.get("insight"):
            lines = [l.strip() for l in r["insight"].split("\n") if l.strip()]
            items = "".join(f"<li>{l.lstrip('•').strip()}</li>" for l in lines)
            insight_html = f"<ul class='insight-list'>{items}</ul>"

        route_badge = (
            "<span class='badge sql-badge'>SQL</span>"
            if r.get("route") == "SQL"
            else "<span class='badge sem-badge'>SEMANTIC</span>"
        )

        panels_html += f"""
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">{r['sub_question']}</div>
            {route_badge}
          </div>
          <div class="table-area">{table_html}</div>
          <div class="insight-area">
            <div class="insight-label">Key Insights</div>
            {insight_html}
          </div>
        </div>"""

    narrative_paragraphs = "".join(
        f"<p>{p.strip()}</p>"
        for p in narrative.split("\n")
        if p.strip()
    )

    return f"""
    <style>
      .dashboard-root * {{ box-sizing: border-box; }}
      .dashboard-root,
      .dashboard-root p,
      .dashboard-root div,
      .dashboard-root li,
      .dashboard-root td,
      .dashboard-root th,
      .dashboard-root span {{ color: #1e1e1e !important; }}
      .dashboard-root .dashboard-header,
      .dashboard-root .dashboard-header h2,
      .dashboard-root .dashboard-header p {{ color: white !important; }}
      .dashboard-root .sql-badge {{ color: #1e40af !important; }}
      .dashboard-root .sem-badge {{ color: #15803d !important; }}
      .dashboard-root .panel-title {{ color: #1F4E79 !important; }}
      .dashboard-root .insight-label {{ color: #1F4E79 !important; }}
      .dashboard-root .narrative-title {{ color: #1F4E79 !important; }}
      .dashboard-header {{
        background: linear-gradient(135deg, #1F4E79, #2E86C1);
        color: white;
        padding: 20px 28px;
        border-radius: 10px;
        margin-bottom: 24px;
      }}
      .dashboard-header h2 {{ margin: 0 0 6px 0; font-size: 1.4em; }}
      .dashboard-header p  {{ margin: 0; opacity: 0.85; font-size: 0.9em; }}
      .panel-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 20px;
        margin-bottom: 24px;
      }}
      .panel {{
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        padding: 18px;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }}
      .panel-header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 8px;
      }}
      .panel-title {{
        font-weight: 600;
        font-size: 0.95em;
        color: #1F4E79;
        line-height: 1.4;
        flex: 1;
      }}
      .badge {{
        font-size: 0.7em;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
        white-space: nowrap;
        margin-top: 2px;
      }}
      .sql-badge {{ background: #dbeafe; color: #1e40af; }}
      .sem-badge {{ background: #dcfce7; color: #15803d; }}
      .table-area {{ overflow-x: auto; font-size: 0.82em; }}
      .data-table {{ width: 100%; border-collapse: collapse; }}
      .data-table th {{
        background: #1F4E79;
        color: white !important;
        padding: 6px 10px;
        text-align: left;
        font-weight: 600;
      }}
      .data-table td {{
        padding: 5px 10px;
        border-bottom: 1px solid #e5e7eb;
        color: #374151;
      }}
      .data-table tr:hover td {{ background: #f9fafb; }}
      .insight-area {{
        background: #f8fafc;
        border-left: 4px solid #2E86C1;
        border-radius: 4px;
        padding: 10px 14px;
      }}
      .insight-label {{
        font-weight: 700;
        font-size: 0.8em;
        color: #1F4E79;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
      }}
      .insight-list {{
        margin: 0;
        padding-left: 18px;
        font-size: 0.85em;
        color: #374151;
        line-height: 1.6;
      }}
      .error-panel {{ border: 2px solid #fee2e2; }}
      .error-msg {{ color: #dc2626; font-size: 0.85em; }}
      .narrative-section {{
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        padding: 24px 28px;
      }}
      .narrative-title {{
        font-size: 1.1em;
        font-weight: 700;
        color: #1F4E79;
        margin-bottom: 14px;
        padding-bottom: 10px;
        border-bottom: 2px solid #e5e7eb;
      }}
      .narrative-section p {{
        color: #374151;
        line-height: 1.75;
        margin-bottom: 12px;
        font-size: 0.92em;
      }}
    </style>

    <div class="dashboard-root">
      <div class="dashboard-header">
        <h2>📊 Dashboard: {user_query}</h2>
        <p>{len(results)} panel(s) generated automatically</p>
      </div>
      <div class="panel-grid">
        {panels_html}
      </div>
      <div class="narrative-section">
        <div class="narrative-title">📝 Executive Summary</div>
        {narrative_paragraphs}
      </div>
    </div>
    """

print("[RENDERER] render_dashboard defined.")