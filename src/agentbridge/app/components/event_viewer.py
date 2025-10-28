import mesop as me
import pandas as pd
from state.state import StateEvent


def flatten_content(content: list[tuple[str, str]]) -> str:
    parts = []
    for p in content:
        if p[1] == "text/plain" or p[1] == "application/json":
            parts.append(p[0])
        else:
            parts.append(p[1])

    return "\n".join(parts)


@me.component
def event_list(events: list[StateEvent]) -> None:
    """Events list component."""
    df_data = {
        "Conversation ID": [],
        "Actor": [],
        "Role": [],
        "Id": [],
        "Content": [],
    }
    # events = asyncio.run(GetEvents())
    for e in events:
        # event = convert_event_to_state(e)
        df_data["Conversation ID"].append(e.context_id)
        df_data["Role"].append(e.role)
        df_data["Id"].append(e.id)
        df_data["Content"].append(flatten_content(e.content))
        df_data["Actor"].append(e.actor)
    if not df_data["Conversation ID"]:
        me.text(
            "No events available at the moment.",
            style=me.Style(
                text_align="center",
                color=me.theme_var("on-surface-variant"),
                font_size="16px",
                margin=me.Margin(top=5, bottom=32),
            ),
        )
        return
    df = pd.DataFrame(
        pd.DataFrame(df_data),
        columns=["Conversation ID", "Actor", "Role", "Id", "Content"],
    )
    with me.box(
        style=me.Style(
            display="flex",
            justify_content="space-between",
            flex_direction="column",
        )
    ):
        me.table(
            df,
            header=me.TableHeader(sticky=True),
            columns={
                "Conversation ID": me.TableColumn(sticky=True),
                "Actor": me.TableColumn(sticky=True),
                "Role": me.TableColumn(sticky=True),
                "Id": me.TableColumn(sticky=True),
                "Content": me.TableColumn(sticky=True),
            },
        )
