from components.agent_messages import AgentMessages
from state.state import AppState


def agent_messages_page(app_state: AppState):
    AgentMessages(
        app_state.event_list,
        app_state.current_conversation_id,
    )
