import asyncio
import json
import os
from functools import partial

import mesop as me
from components.dialog import dialog, dialog_actions
from components.page_scaffold import page_frame, page_scaffold
from state.agent_state import AgentState
from state.host_agent_service import AddRemoteAgent, ListRemoteAgents
from state.state import AppState
from utils.agent_card import get_agent_card

# Path to your saved agents config
SAVED_AGENTS_PATH = "saved_agents.json"


def load_saved_agents_from_disk() -> list[dict]:
    """
    Returns a list of dicts like: [{"name": "...","address":"host:port"}, ...]
    Accepts these JSON shapes:
      A) {"agents":[{"name":"x","address":"y"}, ...]}
      B) {"Name":"host:port", "Other":"host:port"}
      C) [{"name":"x","address":"y"}, ...]
    """
    if not os.path.exists(SAVED_AGENTS_PATH):
        return []
    try:
        with open(SAVED_AGENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        if (
            isinstance(data, dict)
            and "agents" in data
            and isinstance(data["agents"], list)
        ):
            return [
                {
                    "name": str(item.get("name", "")),
                    "address": str(item.get("address", "")),
                }
                for item in data["agents"]
                if isinstance(item, dict) and "name" in item and "address" in item
            ]

        if isinstance(data, dict):
            return [{"name": str(k), "address": str(v)} for k, v in data.items()]

        if isinstance(data, list):
            out = []
            for item in data:
                if isinstance(item, dict) and "name" in item and "address" in item:
                    out.append(
                        {"name": str(item["name"]), "address": str(item["address"])}
                    )
            return out

        return []
    except Exception:
        # Fail quietly; the dialog simply won't show saved buttons
        return []


def pick_saved_agent(address: str):
    """Fill the address input with a saved agent's address and clear previous
    details."""
    state = me.state(AgentState)
    state.agent_address = address
    state.error = None
    state.agent_name = ""
    state.agent_description = ""
    state.agent_framework_type = ""
    state.input_modes = []
    state.output_modes = []
    state.stream_supported = None
    state.push_notifications_supported = None


def agent_list_page(app_state: AppState):
    state = me.state(AgentState)

    with page_scaffold():
        with page_frame():
            # Outer column centers everything in main content area (not the whole screen)
            with me.box(
                style=me.Style(
                    width="100%",
                    max_width=900,
                    margin=me.Margin(left="auto", right="auto", top=0, bottom=0),
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                )
            ):
                # Heading
                me.text(
                    "Remote Agents",
                    style=me.Style(
                        text_align="center",
                        font_weight="bold",
                        font_size="2rem",
                        margin=me.Margin(top=30, bottom=4),
                        letter_spacing=1,
                        color=me.theme_var("on-background"),
                    ),
                )
                # Subtitle
                me.text(
                    "Connect and view your remote agents easily.",
                    style=me.Style(
                        text_align="center",
                        color=me.theme_var("on-background"),
                        font_size="15px",
                        margin=me.Margin(bottom=22),
                    ),
                )
                # Add Agent Button, always visible
                with me.box(
                    style=me.Style(
                        display="flex",
                        justify_content="center",
                        margin=me.Margin(bottom=28),
                    )
                ):
                    me.button(
                        "Add Agent",
                        on_click=lambda e: open_add_agent_dialog(),
                        style=me.Style(
                            background=me.theme_var("surface-container"),
                            color=me.theme_var("on-surface"),
                            border_radius=6,
                            font_size="15px",
                            font_weight="bold",
                            padding=me.Padding(top=10, bottom=10, left=20, right=20),
                            box_shadow="none",
                        ),
                    )

                # List Remote Agents and show in premium card style
                agents = asyncio.run(ListRemoteAgents())
                if agents:
                    with me.box(
                        style=me.Style(
                            border_radius=18,
                            box_shadow="0 8px 24px rgba(0,0,0,0.10)",
                            padding=me.Padding(top=28, bottom=28, left=28, right=28),
                            margin=me.Margin(bottom=35, top=0, left=0, right=0),
                            max_width=900,
                            min_width=340,
                            width="100%",
                            # background=me.theme_var("surface-container-highest")
                        )
                    ):
                        for agent in agents:
                            with me.box(
                                style=me.Style(
                                    display="flex",
                                    flex_direction="column",
                                    gap=6,
                                    background=me.theme_var("surface-container"),
                                    border_radius=12,
                                    box_shadow="0 2px 8px rgba(0,0,0,0.07)",
                                    padding=me.Padding(
                                        top=14, bottom=14, left=18, right=18
                                    ),
                                    margin=me.Margin(bottom=15),
                                )
                            ):
                                me.text(
                                    f"{getattr(agent, 'name', '')}",
                                    style=me.Style(
                                        font_weight="bold",
                                        font_size="0.95rem",
                                        color=me.theme_var("on-surface-variant"),
                                    ),
                                )
                                if getattr(agent, "description", None):
                                    me.text(
                                        f"{getattr(agent, 'description', '')}",
                                        style=me.Style(
                                            color=me.theme_var("on-surface-variant"),
                                            font_size="13px",
                                        ),
                                    )
                                info = []
                                if getattr(agent, "framework", None):
                                    info.append(
                                        f"Framework: {getattr(agent, 'framework', '')}"
                                    )
                                if getattr(agent, "input_modes", None):
                                    info.append(
                                        f"Input: {', '.join(getattr(agent, 'input_modes', []))}"
                                    )
                                if getattr(agent, "output_modes", None):
                                    info.append(
                                        f"Output: {', '.join(getattr(agent, 'output_modes', []))}"
                                    )
                                if getattr(agent, "stream_supported", None) is not None:
                                    info.append(
                                        f"Streaming: {'Yes' if getattr(agent, 'stream_supported', False) else 'No'}"
                                    )
                                if (
                                    getattr(agent, "push_notifications_supported", None)
                                    is not None
                                ):
                                    info.append(
                                        f"Push Notifications: {'Yes' if getattr(agent, 'push_notifications_supported', False) else 'No'}"
                                    )
                                if info:
                                    me.text(
                                        " | ".join(info),
                                        style=me.Style(
                                            font_size="12px",
                                            color=me.theme_var("on-surface-variant"),
                                            margin=me.Margin(top=5),
                                        ),
                                    )
                # Dialog for adding agent (centered in same column)
                with dialog(state.agent_dialog_open):
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="column",
                            gap=8,
                            padding=me.Padding(top=18, bottom=18, left=18, right=18),
                            # background=me.theme_var("surface-container-highest"),
                            border_radius=16,
                            box_shadow="0 4px 18px rgba(0,0,0,0.22)",
                            min_width=340,
                            max_width=600,
                            margin=me.Margin(top=15),
                        )
                    ):
                        me.text(
                            "Add a New Agent",
                            style=me.Style(
                                font_weight="bold",
                                font_size="1.18rem",
                                color=me.theme_var("on-background"),
                                margin=me.Margin(bottom="14px"),
                                text_align="center",
                            ),
                        )

                        # Saved agents quick-pick
                        if state.saved_agents:
                            me.text(
                                "Saved agents",
                                style=me.Style(
                                    font_weight="bold",
                                    font_size="0.9rem",
                                    color=me.theme_var("on-surface-variant"),
                                    margin=me.Margin(bottom=4, top=2),
                                    text_align="center",  # <-- Center the title
                                ),
                            )
                            with me.box(
                                style=me.Style(
                                    display="flex",
                                    flex_wrap="wrap",
                                    gap=6,
                                    margin=me.Margin(bottom=8),
                                    justify_content="center",  # <-- Center the buttons
                                )
                            ):

                                def handle_saved_agent_click(name, addr, e=None):
                                    print(f"Button clicked: {name} @ {addr}")
                                    pick_saved_agent(addr)

                                for item in state.saved_agents:
                                    name = item.get("name", "")
                                    addr = item.get("address", "")
                                    if not name or not addr:
                                        continue

                                    me.button(
                                        name,
                                        on_click=partial(
                                            handle_saved_agent_click, name, addr
                                        ),
                                        style=me.Style(
                                            background=me.theme_var(
                                                "surface-container"
                                            ),
                                            color=me.theme_var("on-surface"),
                                            border_radius=9999,
                                            font_size="12px",
                                            padding=me.Padding(
                                                top=6, bottom=6, left=10, right=10
                                            ),
                                            box_shadow="none",
                                        ),
                                    )

                        # Address input (bound to state so clicking a saved-agent fills it)
                        me.input(
                            label="Agent Address",
                            on_blur=set_agent_address,
                            placeholder="e.g. localhost:10011",
                            value=state.agent_address,  # <-- bind value (NEW)
                            style=me.Style(
                                border_radius=3,
                                padding=me.Padding(
                                    top=10, bottom=10, left=10, right=10
                                ),
                                font_size="14px",
                                font_weight="500",
                                background=me.theme_var("surface-container"),
                                color=me.theme_var("on-surface"),
                                width="100%",
                                margin=me.Margin(bottom=10),
                            ),
                        )

                        if state.error:
                            me.text(
                                state.error,
                                style=me.Style(
                                    color="red",
                                    font_weight="bold",
                                    margin=me.Margin(top=10),
                                ),
                            )

                        info_style = me.Style(
                            font_size="14px",
                            color=me.theme_var("on-surface-variant"),
                            font_weight="normal",
                        )

                        if state.agent_name:
                            me.text(
                                f"Name: {state.agent_name}",
                                style=me.Style(
                                    font_size="14px",
                                    color=me.theme_var("on-surface-variant"),
                                    font_weight="bold",
                                ),
                            )
                        if state.agent_description:
                            me.text(
                                f"Description: {state.agent_description}",
                                style=me.Style(
                                    font_size="14px",
                                    color=me.theme_var("on-surface-variant"),
                                    font_weight="bold",
                                ),
                            )
                        if state.agent_framework_type:
                            me.text(
                                f"Framework: {state.agent_framework_type}",
                                style=info_style,
                            )
                        if state.input_modes:
                            me.text(
                                f'Input: {", ".join(state.input_modes)}',
                                style=info_style,
                            )
                        if state.output_modes:
                            me.text(
                                f'Output: {", ".join(state.output_modes)}',
                                style=info_style,
                            )
                        if state.agent_name:
                            me.text(
                                f"Streaming: {state.stream_supported}", style=info_style
                            )
                            me.text(
                                f"Push Notifications: {state.push_notifications_supported}",
                                style=info_style,
                            )

                    with dialog_actions():
                        btn_style_primary = me.Style(
                            background=me.theme_var("surface-container"),
                            color=me.theme_var("on-surface"),
                            border_radius=6,
                            padding=me.Padding(top=6, bottom=6, left=12, right=12),
                            font_size="13px",
                            font_weight="bold",
                            box_shadow="none",
                        )
                        btn_style_secondary = me.Style(
                            background=me.theme_var("surface-container-low"),
                            color=me.theme_var("on-surface"),
                            border_radius=6,
                            padding=me.Padding(top=6, bottom=6, left=12, right=12),
                            font_size="13px",
                        )

                        if not state.agent_name:
                            me.button(
                                "Read Info",
                                on_click=load_agent_info,
                                style=btn_style_primary,
                            )
                        elif not state.error:
                            me.button(
                                "Save Agent",
                                on_click=save_agent,
                                style=btn_style_primary,
                            )

                        me.button(
                            "Cancel",
                            on_click=cancel_agent_dialog,
                            style=btn_style_secondary,
                        )


# Helper to open the add agent dialog
def open_add_agent_dialog():
    state = me.state(AgentState)
    state.agent_dialog_open = True
    state.agent_address = ""
    state.agent_name = ""
    state.agent_description = ""
    state.agent_framework_type = ""
    state.input_modes = []
    state.output_modes = []
    state.stream_supported = None
    state.push_notifications_supported = None
    state.error = None

    # Load saved agents from disk (NEW)
    state.saved_agents = load_saved_agents_from_disk()


def set_agent_address(e: me.InputBlurEvent):
    state = me.state(AgentState)
    state.agent_address = e.value


def load_agent_info(e: me.ClickEvent):
    state = me.state(AgentState)
    try:
        state.error = None
        agent_card_response = get_agent_card(state.agent_address)
        state.agent_name = agent_card_response.name
        state.agent_description = agent_card_response.description
        state.agent_framework_type = (
            agent_card_response.provider.organization
            if agent_card_response.provider
            else ""
        )
        state.input_modes = agent_card_response.defaultInputModes
        state.output_modes = agent_card_response.defaultOutputModes
        state.stream_supported = agent_card_response.capabilities.streaming
        state.push_notifications_supported = (
            agent_card_response.capabilities.pushNotifications
        )
    except Exception:
        print(e)
        state.agent_name = None
        state.error = f"Cannot connect to agent: {state.agent_address}"


def cancel_agent_dialog(e: me.ClickEvent):
    state = me.state(AgentState)
    state.agent_dialog_open = False


async def save_agent(e: me.ClickEvent):
    state = me.state(AgentState)
    await AddRemoteAgent(state.agent_address)
    state.agent_address = ""
    state.agent_name = ""
    state.agent_description = ""
    state.agent_dialog_open = False
