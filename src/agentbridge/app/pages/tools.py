import asyncio

import mesop as me
from components.side_nav import sidenav
from components.tools_list import tools_list
from state.tools_state import fetch_tools


def tools_list_page(app_state):
    try:
        tools = asyncio.run(fetch_tools())
    except RuntimeError:
        tools = asyncio.get_event_loop().run_until_complete(fetch_tools())
    except Exception as e:
        print("Error fetching tools:", e)
        tools = []
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            width="100vw",
            height="100vh",
        )
    ):
        # Sidebar
        sidenav("/tools")  # pass the route for active state
        # Main Content
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="column",
                align_items="center",
                width="100%",
                padding=me.Padding(top=30),
            )
        ):
            me.text(
                "Tools",
                style=me.Style(
                    text_align="center",
                    font_weight="bold",
                    font_size="2rem",
                    margin=me.Margin(top=30, bottom=8),
                    letter_spacing=1,
                    color=me.theme_var("on-background"),
                ),
            )
            me.text(
                "View all available MCP tools below.",
                style=me.Style(
                    text_align="center",
                    color=me.theme_var("on-background"),
                    font_size="15px",
                    margin=me.Margin(bottom=24),
                ),
            )
            tools_list(tools)
