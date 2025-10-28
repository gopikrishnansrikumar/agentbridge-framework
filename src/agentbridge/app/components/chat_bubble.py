import mesop as me
from state.state import AppState, StateMessage


@me.component
def chat_bubble(message: StateMessage, key: str):
    """Chat bubble component."""
    app_state = me.state(AppState)
    show_progress_bar = (
        message.message_id in app_state.background_tasks
        or message.message_id in app_state.message_aliases.values()
    )
    progress_text = ""
    if show_progress_bar:
        progress_text = app_state.background_tasks[message.message_id]
    if not message.content:
        print("No message content")
    for pair in message.content:
        chat_box(
            pair[0],
            pair[1],
            message.role,
            key,
            progress_bar=show_progress_bar,
            progress_text=progress_text,
        )


def chat_box(
    content: str,
    media_type: str,
    role: str,
    key: str,
    progress_bar: bool,
    progress_text: str,
):
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            align_items="flex-end" if role == "user" else "flex-start",
            width="100%",
            margin=me.Margin(top="4px", bottom="4px"),
        ),
        key=key,
    ):
        with me.box(
            style=me.Style(
                max_width="65%",
                background=(
                    me.theme_var("surface-container-highest")
                    if role == "user"
                    else me.theme_var("surface-container-low")
                ),
                color=me.theme_var("on-surface"),
                border_radius=16,
                padding=me.Padding(top="5px", left="12px", right="12px", bottom="5px"),
                font_size="10px",
                margin=me.Margin(
                    left="auto" if role == "user" else "0px",
                    right="auto" if role != "user" else "0px",
                ),
                box_shadow="0 2px 8px rgba(0,0,0,0.05)",
            ),
        ):
            if media_type == "image/png":
                if "/message/file" not in content:
                    content = "data:image/png;base64," + content
                me.image(
                    src=content,
                    style=me.Style(
                        width="80%",
                        object_fit="contain",
                        border_radius=10,
                        margin=me.Margin(bottom="8px"),
                    ),
                )
            else:
                me.markdown(content)

    # Optional: progress bar (same alignment)
    if progress_bar:
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="column",
                align_items="flex-end" if role == "user" else "flex-start",
                width="100%",
            ),
            key=key + "_progress",
        ):
            with me.box(
                style=me.Style(
                    max_width="65%",
                    background=me.theme_var("surface-container-low"),
                    color=me.theme_var("on-surface-variant"),
                    border_radius=16,
                    padding=me.Padding(
                        top="8px", left="14px", right="14px", bottom="8px"
                    ),
                    font_size="12px",
                    margin=me.Margin(
                        left="auto" if role == "user" else "0px",
                        right="auto" if role != "user" else "0px",
                    ),
                ),
            ):
                me.text(
                    progress_text or "Working...",
                    style=me.Style(font_size="12px", margin=me.Margin(bottom="4px")),
                )
                me.progress_bar(color="accent")
