import json
import os
import xml.dom.minidom
from pathlib import Path
from urllib.parse import urlparse

import httpx
import mesop as me
from dotenv import load_dotenv
from state.state import AppState, StateEvent


@me.stateclass
class AutoScrollState:
    """UI state toggle for enabling/disabling auto-scroll of messages."""
    auto_scroll: bool = True


# === Load environment variables ===
APP_DIR = Path(__file__).resolve().parents[1]
load_dotenv(APP_DIR / ".env")


# === Delegator base URL helper ===
def _delegator_base() -> str:
    """Return DELEGATOR_URL without trailing slash (default localhost:12000)."""
    url = (os.getenv("DELEGATOR_URL") or "http://localhost:12000").strip()
    if not urlparse(url).scheme:
        url = "http://" + url
    return url.rstrip("/")


DELEGATOR_URL = _delegator_base()


# ---------------- Utility functions ----------------
def normalize_actor(a: str) -> str:
    """Rename `user` to Orchestrator for display clarity."""
    return "Orchestrator" if a == "user" else a


def extract_message_text(parts):
    """Flatten a message’s text parts into a single string."""
    return "".join([text for text, kind in parts if "text" in kind])


def fetch_agents():
    """Query Delegator for a list of available agents."""
    try:
        resp = httpx.post(
            f"{DELEGATOR_URL}/agent/list",
            json={"jsonrpc": "2.0", "id": "x", "method": "agent/list"},
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        print("Error fetching agents", e)
        return []


def fetch_events():
    """Query Delegator for all past events/messages."""
    try:
        resp = httpx.post(
            f"{DELEGATOR_URL}/events/get",
            json={"jsonrpc": "2.0", "id": "x", "method": "events/get"},
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        print("Error fetching events", e)
        return []


def filter_valid_messages(events):
    """Filter out invalid or trivial messages (e.g., too short)."""
    out = []
    for ev in events:
        if not hasattr(ev, "content") or not ev.content:
            continue
        if any(
            len(text) <= 2 and len(ev.content) > 3
            for (text, kind) in ev.content
            if "text" in kind
        ):
            continue
        out.append(ev)
    return out


def group_messages_by_actor(msgs):
    """Group messages by actor for easier display."""
    out = {}
    for m in msgs:
        actor = normalize_actor(m.actor)
        out.setdefault(actor, []).append(m)
    return out


def get_agent_tiles(agents):
    """Extract agent names to display as tiles."""
    return [a.get("name") for a in agents if a.get("name")]


def should_display_message(txt):
    """Skip control/state messages that should not appear in UI."""
    return "TaskState" not in txt


def pretty_xml(xml_str):
    """Return nicely indented XML string if possible."""
    try:
        dom = xml.dom.minidom.parseString(xml_str)
        pretty = dom.toprettyxml(indent="  ")
        return "\n".join([line for line in pretty.splitlines() if line.strip()])
    except Exception:
        return xml_str


def find_and_markdown_structures(text: str) -> str:
    """Scan text for JSON/XML blocks and pretty-print them in markdown code fences."""
    results = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] in "{[":
            # Try to parse JSON-like block
            stack = [text[i]]
            start = i
            i += 1
            while i < n and stack:
                if text[i] == stack[-1]:
                    stack.append(text[i])
                elif (stack[-1] == "{" and text[i] == "}") or (
                    stack[-1] == "[" and text[i] == "]"
                ):
                    stack.pop()
                elif text[i] in "{[":
                    stack.append(text[i])
                i += 1
            candidate = text[start:i]
            try:
                parsed = json.loads(candidate)
                pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
                results.append(f"\n```json\n{pretty}\n```\n")
            except Exception:
                results.append(candidate)
        elif text[i] == "<":
            # Try to parse XML block
            start = i
            end = text.find(">", i)
            if end == -1:
                results.append(text[i])
                i += 1
                continue
            tag_end = text.find(">", i)
            if tag_end != -1:
                tag_name = text[i + 1 : tag_end].split()[0].replace("/", "")
                close_tag = f"</{tag_name}>"
                close_idx = text.find(close_tag, tag_end)
                if close_idx != -1:
                    candidate = text[start : close_idx + len(close_tag)]
                    pretty = pretty_xml(candidate)
                    results.append(f"\n```xml\n{pretty}\n```\n")
                    i = close_idx + len(close_tag)
                    continue
            results.append(text[i])
            i += 1
        else:
            results.append(text[i])
            i += 1
    return "".join(results)


# ---------------- Main UI Component ----------------
def AgentMessages(events: list[StateEvent], current_conversation_id: str | None = None):
    """Render the agent messaging panel showing conversations across Orchestrator, Delegator, and agents."""
    state = me.state(AppState)
    auto_state = me.state(AutoScrollState)

    agents = fetch_agents()
    get_agent_tiles(agents)  # currently not shown in UI
    messages = filter_valid_messages(events)

    # Ensure persistent per-agent color assignments
    if not hasattr(state, "agent_colors"):
        state.agent_colors = {}
    if not hasattr(state, "_palette_index"):
        state._palette_index = 0

    PALETTE = [
        "#E57373", "#64B5F6", "#81C784", "#FFD54F",
        "#BA68C8", "#4DB6AC", "#FF8A65", "#A1887F",
        "#90A4AE", "#F06292", "#7986CB", "#AED581",
        "#FFB74D", "#4FC3F7", "#9575CD", "#4DB6AC",
    ]

    def color_for(name: str) -> str:
        """Assign each agent a consistent color from palette."""
        if name not in state.agent_colors:
            state.agent_colors[name] = PALETTE[state._palette_index % len(PALETTE)]
            state._palette_index += 1
        return state.agent_colors[name]

    # Helpers for event lookups
    def _get_context_id(x):
        if isinstance(x, dict):
            return (
                x.get("context_id")
                or x.get("contextId")
                or (x.get("content") or {}).get("context_id")
                or (x.get("content") or {}).get("contextId")
            )
        content = getattr(x, "content", None)
        return (
            getattr(x, "context_id", None)
            or (getattr(content, "context_id", None) if content else None)
            or (getattr(content, "contextId", None) if content else None)
        )

    def _get_timestamp(x):
        return (
            x.get("timestamp", 0) if isinstance(x, dict) else getattr(x, "timestamp", 0)
        )

    # Build mapping of context_id -> latest timestamp
    events_full = fetch_events()
    event_ts_lookup = {}
    for ev in events_full:
        cid = _get_context_id(ev)
        ts = _get_timestamp(ev)
        if cid:
            event_ts_lookup[cid] = max(ts, event_ts_lookup.get(cid, 0))

    def get_ts(msg):
        cid = _get_context_id(msg)
        return event_ts_lookup.get(cid, 0)

    # Collect conversation IDs ordered by recency
    all_context_ids = sorted(
        set(ev.context_id for ev in messages),
        key=lambda cid: max(get_ts(ev) for ev in messages if ev.context_id == cid),
        reverse=True,
    )

    if not hasattr(state, "current_conversation_id"):
        state.current_conversation_id = None
    if not hasattr(state, "show_convo_selector"):
        state.show_convo_selector = False

    # Pick most recent conversation if none selected
    if all_context_ids and (state.current_conversation_id not in all_context_ids):
        state.current_conversation_id = all_context_ids[0]
    if not all_context_ids:
        state.current_conversation_id = None

    def short_context_label(cid, messages):
        """Format conversation ID + timestamp for display."""
        import datetime
        match_msg = next((m for m in messages if m.context_id == cid), None)
        ts = get_ts(match_msg) if match_msg else 0
        dt = datetime.datetime.fromtimestamp(ts) if ts else ""
        return f"{cid[:4]}...{cid[-4:]} ({dt.strftime('%b %d, %H:%M') if ts else ''})"

    # Select conversation
    selected_id = current_conversation_id or state.current_conversation_id
    filtered_messages = [
        m for m in messages if selected_id and m.context_id == selected_id
    ]
    group_messages_by_actor(filtered_messages)

    # ---------------- UI Layout ----------------
    with me.box(
        style=me.Style(
            width="100%",
            max_width=2500,
            margin=me.Margin(left="auto", right="auto"),
            display="flex",
            flex_direction="column",
            align_items="center",
        )
    ):
        # Header
        me.text(
            "Agent Conversations",
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
            "Messages from Orchestrator, Delegator, and connected agents.",
            style=me.Style(
                text_align="center",
                color=me.theme_var("on-background"),
                font_size="15px",
                margin=me.Margin(bottom=16),
            ),
        )

        # Auto-scroll toggle + conversation label
        auto_state = me.state(AutoScrollState)
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                align_items="center",
                gap=8,
                margin=me.Margin(bottom=12),
            )
        ):
            with me.tooltip(message="Auto-scroll"):
                me.slide_toggle(
                    label="",
                    on_change=lambda e: setattr(
                        auto_state, "auto_scroll", not auto_state.auto_scroll
                    ),
                )

            if selected_id:
                me.text("Conversation: ", style=me.Style(font_weight="bold", font_size="1.08rem"))
                me.text(
                    short_context_label(selected_id, messages),
                    style=me.Style(
                        font_family="monospace",
                        font_size="1.03rem",
                        background=me.theme_var("surface-container-low"),
                        padding=me.Padding(top=2, bottom=2, left=10, right=10),
                        border_radius=6,
                        margin=me.Margin(right=8),
                    ),
                )
            else:
                me.text(
                    "Start a conversation to view messages.",
                    style=me.Style(
                        font_size="1.07rem",
                        font_style="italic",
                        color=me.theme_var("on-surface-variant"),
                        margin=me.Margin(left=3, top=6),
                    ),
                )

        if selected_id:
            conv_msgs = [m for m in messages if m.context_id == selected_id]

            # Determine participants; Orchestrator + Delegator always first
            participants_set = {normalize_actor(m.actor) for m in conv_msgs}
            head = [p for p in ["Orchestrator", "Delegator"] if p in participants_set]
            tail = sorted([p for p in participants_set if p not in {"Orchestrator", "Delegator"}])
            participants = head + tail

            # Messages sorted chronologically
            ordered = sorted(conv_msgs, key=get_ts)

            # Track "active speaker" (most recent sender)
            if ordered:
                last_msg = ordered[-1]
                current_speaker = normalize_actor(last_msg.actor)
                last_ts = get_ts(last_msg)

                if not hasattr(state, "_active_speaker"):
                    state._active_speaker = None
                if not hasattr(state, "_active_speaker_ts"):
                    state._active_speaker_ts = 0

                if (
                    state._active_speaker != current_speaker
                    or state._active_speaker_ts != last_ts
                ):
                    state._active_speaker = current_speaker
                    state._active_speaker_ts = last_ts
            else:
                state._active_speaker = None
                state._active_speaker_ts = 0

            # Participant chips (highlight active speaker with a ring)
            with me.box(
                style=me.Style(
                    width="100%",
                    max_width=1100,
                    display="flex",
                    flex_direction="row",
                    flex_wrap="wrap",
                    gap=10,
                    justify_content="center",
                    align_items="center",
                    margin=me.Margin(bottom=14),
                )
            ):
                for name in participants:
                    active = name == getattr(state, "_active_speaker", None)
                    ring_color = color_for(name) if active else "transparent"
                    chip_bg = me.theme_var("surface-container")
                    chip_shadow = "0 2px 8px rgba(0,0,0,0.08)"
                    scale = "1.00"

                    if active:
                        chip_shadow = "0 6px 18px rgba(0,0,0,0.18)"
                        scale = "1.05"

                    # Outer wrapper = glowing ring
                    with me.box(
                        style=me.Style(
                            background=ring_color,
                            border_radius=999,
                            padding=me.Padding(top=2, bottom=2, left=2, right=2),
                            transition="transform 180ms ease, box-shadow 180ms ease, background 180ms ease",
                            transform=f"scale({scale})",
                            box_shadow=chip_shadow,
                            display="inline-flex",
                        )
                    ):
                        # Inner chip with color dot + label
                        with me.box(
                            style=me.Style(
                                background=chip_bg,
                                border_radius=999,
                                padding=me.Padding(top=8, bottom=8, left=14, right=14),
                                display="inline-flex",
                                align_items="center",
                                gap=10,
                            )
                        ):
                            with me.box(
                                style=me.Style(
                                    width=10,
                                    height=10,
                                    border_radius=999,
                                    background=color_for(name),
                                    box_shadow=(
                                        "0 0 0 0 rgba(0,0,0,0)"
                                        if not active
                                        else f"0 0 0 6px {ring_color}22"
                                    ),
                                    transition="box-shadow 180ms ease",
                                )
                            ):
                                pass

                            me.text(
                                name,
                                style=me.Style(
                                    font_weight="800",
                                    color=color_for(name),
                                    font_size="0.98rem",
                                ),
                            )

            # ---------------- Messages area ----------------
            with me.box(
                style=me.Style(
                    width="100%",
                    max_width=1800,
                    height="70vh",
                    background=me.theme_var("surface-container"),
                    border_radius=16,
                    box_shadow="0 8px 24px rgba(0,0,0,0.10)",
                    padding=me.Padding(top=12, bottom=12, left=16, right=16),
                    overflow_y="auto",
                    display="flex",
                    flex_direction="column",
                    gap=8,
                )
            ):
                for idx, msg in enumerate(ordered):
                    actor = normalize_actor(msg.actor)
                    raw = extract_message_text(msg.content)
                    raw_stripped = raw.strip()
                    txt = find_and_markdown_structures(raw)
                    if not raw_stripped or not should_display_message(txt):
                        continue

                    is_inline = ("\n" not in raw_stripped) and (
                        not raw_stripped.startswith("```")
                    )
                    is_last = idx == len(ordered) - 1
                    accent = (
                        color_for(actor)
                        if is_last
                        else me.theme_var("surface-container-low")
                    )

                    # Row = accent bar + bubble
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            align_items="stretch",
                            gap=4,
                        ),
                        key="last_msg" if is_last else None,
                    ):
                        # Accent bar
                        with me.box(
                            style=me.Style(
                                width=4,
                                background=accent,
                                border_radius=4,
                                transition="background 160ms ease",
                            )
                        ):
                            pass

                        # Bubble
                        with me.box(
                            style=me.Style(
                                background=me.theme_var("surface-container-low"),
                                border_radius=10,
                                padding=me.Padding(top=2, bottom=2, left=12, right=12),
                                width="fit-content",
                                max_width="100%",
                                word_wrap="break-word",
                                box_shadow="0 1px 4px rgba(0,0,0,0.06)",
                            )
                        ):
                            if is_inline:
                                with me.box(
                                    style=me.Style(
                                        display="inline-flex",
                                        align_items="baseline",
                                        gap=2,
                                        flex_wrap="wrap",
                                    )
                                ):
                                    me.text(
                                        f"{actor}:",
                                        style=me.Style(
                                            font_weight="bold",
                                            display="inline",
                                            color=color_for(actor),
                                        ),
                                    )
                                    me.markdown(
                                        txt,
                                        style=me.Style(
                                            display="inline",
                                            font_size="15px",
                                            color=me.theme_var("on-surface"),
                                            font_weight="500",
                                        ),
                                    )
                            else:
                                me.text(
                                    f"{actor}:",
                                    style=me.Style(
                                        font_weight="bold",
                                        display="inline",
                                        color=color_for(actor),
                                    ),
                                )
                                me.markdown(
                                    txt,
                                    style=me.Style(
                                        font_size="15px",
                                        color=me.theme_var("on-surface"),
                                        font_family="inherit",
                                        font_weight="500",
                                        word_wrap="break-word",
                                    ),
                                )

                # Auto-scroll when toggle is ON
                if not me.state(AutoScrollState).auto_scroll:
                    me.scroll_into_view(key="last_msg")
