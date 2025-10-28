import mesop as me
from components.conversation import conversation
from components.page_scaffold import page_frame, page_scaffold
from state.state import AppState


def conversation_page(app_state: AppState):
    """Conversation Page."""
    with page_scaffold():
        with page_frame():
            me.text(
                "Conversations",
                style=me.Style(
                    text_align="center",
                    font_weight="bold",
                    font_size="2rem",
                    margin=me.Margin(top=30, bottom=4),
                    letter_spacing=1,
                    color=me.theme_var("on-background"),
                ),
            )
            me.text(
                "Talk with your agent below.",
                style=me.Style(
                    text_align="center",
                    color=me.theme_var("on-background"),
                    font_size="15px",
                    margin=me.Margin(bottom=22),
                ),
            )
            conversation()
