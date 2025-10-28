import mesop as me
from components.conversation_list import conversation_list
from components.page_scaffold import page_frame
from state.host_agent_service import CreateConversation
from state.state import AppState


@me.stateclass
class PageState:
    """Local Page State."""

    temp_name: str = ""


def on_blur_set_name(e: me.InputBlurEvent):
    """Input handler."""
    state = me.state(PageState)
    state.temp_name = e.value


def on_enter_change_name(
    e: me.components.input.input.InputEnterEvent,
):  # pylint: disable=unused-argument
    """Change name button handler."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    app_state.name = state.temp_name
    app_state.greeting = ""  # reset greeting
    yield


def on_click_change_name(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Change name button handler."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    app_state.name = state.temp_name
    app_state.greeting = ""  # reset greeting
    yield


async def add_conversation(e: me.ClickEvent):  # unchanged
    response = await CreateConversation()
    me.state(AppState).messages = []
    me.navigate(
        "/conversation",
        query_params={"conversation_id": response.conversation_id},
    )
    yield


def conversations_home_page_content(app_state: AppState):
    """Home Page."""
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            height="100%",
        ),
    ):
        with me.box(
            style=me.Style(
                background=me.theme_var("background"),
                height="100%",
                margin=me.Margin(bottom=20),
            )
        ):
            with me.box(
                style=me.Style(
                    # background=me.theme_var('surface-container-highest'),
                    border_radius=20,
                    box_shadow="0 4px 24px rgba(0,0,0,0.10)",
                    padding=me.Padding(left="32px", right="32px", bottom="32px"),
                    margin=me.Margin(
                        top="5px", bottom="32px", left="auto", right="auto"
                    ),
                    max_width="850px",
                    min_width="340px",
                    width="60vw",
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                )
            ):
                with page_frame():
                    me.text(
                        "Conversations",
                        style=me.Style(
                            text_align="center",
                            font_weight="bold",
                            font_size="2rem",
                            margin=me.Margin(top=30, bottom=4),
                            letter_spacing=1,
                            # color=me.theme_var("on-background")
                        ),
                    )
                    me.text(
                        "Talk with your agent below.",
                        style=me.Style(
                            text_align="center",
                            color=me.theme_var("on-background"),
                            font_size="15px",
                            margin=me.Margin(bottom=4),
                        ),
                    )
                    with me.box(
                        style=me.Style(
                            margin=me.Margin(top="15px"),
                            width="100%",
                            display="flex",
                            justify_content="center",
                        )
                    ):
                        with me.content_button(
                            type="flat",
                            on_click=add_conversation,
                            key="new_conversation",
                            style=me.Style(
                                background=me.theme_var("surface-container"),
                                color=me.theme_var("on-surface"),
                                border_radius=7,
                                font_size="15px",
                                font_weight="bold",
                                box_shadow="none",
                                padding=me.Padding(
                                    top="10px", bottom="10px", left="18px", right="18px"
                                ),
                                # border="1px solid " + me.theme_var("outline-variant"),
                                display="flex",
                                flex_direction="row",
                                gap=5,
                                align_items="center",
                            ),
                        ):
                            # me.icon(icon='add')
                            me.text(
                                "Start Conversation",
                                style=me.Style(font_size="15px", font_weight="bold"),
                            )
                conversation_list(app_state.conversations)
