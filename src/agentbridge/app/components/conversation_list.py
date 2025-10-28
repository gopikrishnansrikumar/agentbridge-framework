import mesop as me
from state.state import AppState, StateConversation


@me.component
def conversation_list(conversations: list[StateConversation]):
    """Styled Conversation List as Cards."""
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            gap=5,
            width="100%",
            align_items="center",
        )
    ):
        for idx, conversation in enumerate(conversations):
            with me.box(
                key=f"conversation_{conversation.conversation_id}",
                style=me.Style(
                    background=me.theme_var("surface-container"),
                    border_radius=14,
                    box_shadow="0 2px 8px rgba(0,0,0,0.06)",
                    padding=me.Padding(
                        top="14px", bottom="14px", left="18px", right="18px"
                    ),
                    margin=me.Margin(bottom="4px"),
                    width="100%",
                    min_width="600px",
                    # border="1px solid " + me.theme_var("outline-variant"),
                    cursor="pointer",
                    transition="box-shadow 0.2s",
                ),
                on_click=lambda e, idx=idx: on_click_card(idx),
            ):
                me.text(
                    f"ID: {conversation.conversation_id}" or "Conversation",
                    style=me.Style(
                        font_weight="bold",
                        font_size="1.1rem",
                        color=me.theme_var("on-surface"),
                        margin=me.Margin(bottom="2px"),
                    ),
                )
                me.text(
                    f"Status: {'Open' if conversation.is_active else 'Closed'}"
                    + f"   |   Messages: {len(conversation.message_ids)}",
                    style=me.Style(
                        color=me.theme_var("on-surface-variant"), font_size="13px"
                    ),
                )


def on_click_card(idx):
    state = me.state(AppState)
    conversation = state.conversations[idx]
    state.current_conversation_id = conversation.conversation_id
    me.query_params.update({"conversation_id": conversation.conversation_id})
    me.navigate("/conversation", query_params=me.query_params)
    yield
