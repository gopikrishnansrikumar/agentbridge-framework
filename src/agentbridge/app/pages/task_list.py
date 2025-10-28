import mesop as me
from components.page_scaffold import page_frame, page_scaffold
from components.task_card import task_card
from state.state import AppState


def task_list_page(app_state: AppState):
    """Task List Page."""
    with page_scaffold():
        with page_frame():
            me.text(
                "Task List",
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
                "See all pending and completed tasks below.",
                style=me.Style(
                    text_align="center",
                    color=me.theme_var("on-background"),
                    font_size="15px",
                    margin=me.Margin(bottom=22),
                ),
            )
            task_card(app_state.task_list)
