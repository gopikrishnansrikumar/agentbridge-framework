import mesop as me
from components.event_viewer import event_list
from components.page_scaffold import page_frame, page_scaffold
from state.state import AppState


def event_list_page(app_state: AppState):
    """Event List Page."""
    with page_scaffold():
        with page_frame():
            me.text(
                "Event List",
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
                "See all recent conversation events below.",
                style=me.Style(
                    text_align="center",
                    color=me.theme_var("on-background"),
                    font_size="15px",
                    margin=me.Margin(bottom=22),
                ),
            )
            event_list(app_state.event_list)
