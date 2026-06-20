from config import gr
from orchestrator import process_query

# Custom CSS to force the columns to align horizontally and vertically center
custom_css = """
.header-row {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
    gap: 10px !important;
}
"""

with gr.Blocks(theme=gr.Theme.from_hub("d8ahazard/rd_blue"), css=custom_css, title="InsightChain") as app:

    # FIX: Wrapped your header elements inside an aligned gr.Row container
    with gr.Row(elem_classes="header-row"):
        with gr.Column(scale=1, min_width=1):
            gr.Image(
                value="assets/InsightChain_cropped_bg_removed.png",
                show_label=False,
                container=False,
                width=300,
                interactive=False,
                buttons=[]
            )

        with gr.Column(scale=5):
            gr.Markdown("""
            # InsightChain Data Analytics and Autonomous BI
            Ask any question about your data in plain English.
            The system automatically creates a full multi-panel dashboard.
            """)

    figures_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=1):
            query_input = gr.Textbox(
                label="Your Question",
                placeholder="e.g. How is our supply chain performing?",
                lines=3
            )
            run_btn = gr.Button("Generate Dashboard", variant="primary", size="lg")
            pipeline_log = gr.Textbox(
                label="Pipeline Log",
                interactive=False,
                lines=18
            )

        with gr.Column(scale=3):
            # Header + tables + insights + narrative first
            dashboard_output = gr.HTML(label="Tables, Insights & Narrative")

            # Charts below
            @gr.render(inputs=figures_state)
            def render_plots(figures):
                if not figures:
                    return
                for i in range(0, len(figures), 2):
                    with gr.Row():
                        gr.Plot(value=figures[i], show_label=False)
                        if i + 1 < len(figures):
                            gr.Plot(value=figures[i + 1], show_label=False)

    run_btn.click(
        fn=process_query,
        inputs=[query_input],
        outputs=[pipeline_log, figures_state, dashboard_output]
    )