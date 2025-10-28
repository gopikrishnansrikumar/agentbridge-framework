from dataclasses import field
from typing import List, Optional

import mesop as me


@me.stateclass
class AgentState:
    agent_dialog_open: bool = False
    agent_address: str = ""
    agent_name: Optional[str] = ""
    agent_description: Optional[str] = ""
    agent_framework_type: Optional[str] = ""
    input_modes: List[str] = field(default_factory=list)
    output_modes: List[str] = field(default_factory=list)
    stream_supported: Optional[bool] = None
    push_notifications_supported: Optional[bool] = None
    error: Optional[str] = None

    # NEW: saved agents rendered as quick-pick buttons in the dialog
    saved_agents: List[dict[str, str]] = field(default_factory=list)
