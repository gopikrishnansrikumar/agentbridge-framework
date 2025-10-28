import mesop as me
from components.api_key_dialog import api_key_dialog
from components.page_scaffold import page_scaffold


def landing_page():
    """Landing Page for Agent Bridge."""
    api_key_dialog()
    with page_scaffold():
        with me.box(
            style=me.Style(
                # width="100%",
                min_height="950vh",
                display="flex",
                flex_direction="column",
                align_items="center",  # This centers all direct children horizontally
                margin=me.Margin(top=60),
            )
        ):
            me.text(
                "Agent Bridge",
                style=me.Style(
                    font_weight="bold",
                    font_size="2.3rem",
                    text_align="center",
                    letter_spacing=2,
                    color=me.theme_var("on-background"),
                    margin=me.Margin(bottom=18),
                ),
            )
            me.text(
                "An application for Multi-Agent communication using A2A and MCP",
                style=me.Style(
                    font_size="1.12rem",
                    color=me.theme_var("on-surface-variant"),
                    text_align="center",
                    margin=me.Margin(bottom=30, left="auto", right="auto"),
                ),
            )
            me.image(
                src="static/architecture.png",  # Make sure this is correct
                alt="Architecture diagram",
                style=me.Style(
                    display="block",
                    width="100%",  # Controls image size responsively
                    max_width="600px",
                    border_radius=12,
                    margin=me.Margin(top=12),
                ),
            )
            # me.text(
            #     "• Add or discover agents and tools\n"
            #     "• Chat with your agents and assign tasks\n"
            #     "• Track conversations, tasks, and agent status\n"
            #     "• Built for seamless integration with LangGraph MCP",
            #     style=me.Style(
            #         font_size="15px",
            #         color=me.theme_var("on-surface-variant"),
            #         text_align="center",
            #         max_width=540,
            #         margin=me.Margin(bottom=40)
            #     )
            # )
