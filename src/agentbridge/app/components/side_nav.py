import mesop as me
from state.state import AppState
from styles.styles import DEFAULT_MENU_STYLE, SIDENAV_MAX_WIDTH, SIDENAV_MIN_WIDTH

page_json = [
    {"display": "Home", "icon": "home", "route": "/"},
    {"display": "Messages", "icon": "message", "route": "/agent_messages"},
    {"display": "Conversations", "icon": "person", "route": "/conversations"},
    {"display": "Agents", "icon": "smart_toy", "route": "/agents"},
    {"display": "Tools", "icon": "build", "route": "/tools"},
    {"display": "Event List", "icon": "list", "route": "/event_list"},
    {"display": "Task List", "icon": "task", "route": "/task_list"},
    {"display": "Settings", "icon": "settings", "route": "/settings"},
]


def on_sidenav_menu_click(e: me.ClickEvent):
    state = me.state(AppState)
    state.sidenav_open = not state.sidenav_open


def navigate_to(e: me.ClickEvent):
    s = me.state(AppState)
    idx = int(e.key)
    if idx >= len(page_json):
        return
    page = page_json[idx]
    s.current_page = page["route"]
    me.navigate(s.current_page)
    yield


def get_menu_style(is_active, minimized):
    # Style for both expanded and minimized items
    base = me.Style(
        background=(
            me.theme_var("surface-container-highest") if is_active else "transparent"
        ),
        border_radius=12 if is_active else 0,
        color=me.theme_var("on-surface-variant"),
        font_weight="bold" if is_active else "normal",
        font_size="15px",
        font_family="inherit",
        padding=me.Padding(top=7, bottom=7, left=10, right=10),
        margin=me.Margin(bottom=2, top=2),
        transition="background 0.1s",
    )
    if minimized:
        base = me.Style(
            background=(
                me.theme_var("surface-container-highest")
                if is_active
                else "transparent"
            ),
            border_radius=12 if is_active else 0,
            margin=me.Margin(bottom=2, top=2),
        )
    return base


@me.component
def sidenav(current_page: str):
    app_state = me.state(AppState)

    with me.sidenav(
        opened=True,
        style=me.Style(
            width=SIDENAV_MAX_WIDTH if app_state.sidenav_open else SIDENAV_MIN_WIDTH,
            background=me.theme_var("surface-container-lowest"),
            # border_right="1px solid " + me.theme_var("outline-variant"),
            box_shadow="0 2px 8px rgba(0,0,0,0.04)",
        ),
    ):
        with me.box(
            style=me.Style(
                margin=me.Margin(top=16, left=16, right=16, bottom=16),
                display="flex",
                flex_direction="column",
                gap=5,
            ),
        ):
            # Top row: menu toggle + branding
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=5,
                    align_items="center",
                ),
            ):
                with me.content_button(
                    type="icon",
                    on_click=on_sidenav_menu_click,
                ):
                    with me.box():
                        with me.tooltip(message="Expand menu"):
                            me.icon(icon="menu")
                if app_state.sidenav_open:
                    me.text(
                        "AGENT BRIDGE",
                        style=me.Style(
                            font_weight="bold",
                            font_size="1.2rem",
                            color=me.theme_var("on-surface"),
                            font_family="inherit",
                            letter_spacing=1,
                            margin=me.Margin(left=4),
                        ),
                    )
            me.box(style=me.Style(height=16))

            # Main menu items
            for idx, page in enumerate(page_json):
                menu_item(
                    idx,
                    page["icon"],
                    page["display"],
                    not app_state.sidenav_open,
                    content_style=get_menu_style(
                        is_active=(page["route"] == current_page),
                        minimized=not app_state.sidenav_open,
                    ),
                )
            # settings & theme toggle
            with me.box(style=MENU_BOTTOM):
                theme_toggle_icon(
                    9,
                    "light_mode",
                    "Theme",
                    not app_state.sidenav_open,
                )


def menu_item(
    key: int,
    icon: str,
    text: str,
    minimized: bool = True,
    content_style: me.Style = DEFAULT_MENU_STYLE,
):
    if minimized:  # minimized
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=5,
                align_items="center",
            ),
        ):
            with me.content_button(
                key=str(key),
                on_click=navigate_to,
                style=content_style,
                type="icon",
            ):
                with me.tooltip(message=text):
                    me.icon(icon=icon)
    else:  # expanded
        with me.content_button(
            key=str(key),
            on_click=navigate_to,
            style=content_style,
        ):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=10,
                    align_items="center",
                ),
            ):
                me.icon(icon=icon)
                me.text(
                    text,
                    style=me.Style(
                        color=content_style.color,
                        font_family="inherit",
                        font_size="15px",
                        font_weight=(
                            "bold" if content_style.font_weight == "bold" else "normal"
                        ),
                    ),
                )


def toggle_theme(e: me.ClickEvent):
    s = me.state(AppState)
    if me.theme_brightness() == "light":
        me.set_theme_mode("dark")
        s.theme_mode = "dark"
    else:
        me.set_theme_mode("light")
        s.theme_mode = "light"


def theme_toggle_icon(key: int, icon: str, text: str, min: bool = True):
    if min:
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=5,
                align_items="center",
            ),
        ):
            with me.content_button(
                key=str(key),
                on_click=toggle_theme,
                type="icon",
            ):
                with me.tooltip(message=text):
                    me.icon(
                        "light_mode" if me.theme_brightness() == "dark" else "dark_mode"
                    )
    else:
        with me.content_button(
            key=str(key),
            on_click=toggle_theme,
        ):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=5,
                    align_items="center",
                    color=me.theme_var("on-surface"),
                ),
            ):
                me.icon(
                    "light_mode" if me.theme_brightness() == "dark" else "dark_mode"
                )
                me.text(
                    "Light mode" if me.theme_brightness() == "dark" else "Dark mode"
                )


MENU_BOTTOM = me.Style(
    display="flex",
    flex_direction="column",
    position="absolute",
    bottom=8,
    align_content="left",
)
