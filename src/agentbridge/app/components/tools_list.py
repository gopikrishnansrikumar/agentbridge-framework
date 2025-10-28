import re

import mesop as me


def parse_docstring(doc):
    result = {
        "summary": "",
        "args": [],
        "returns": None,
    }
    if not doc:
        return result
    summary_match = re.match(r"^(.*?)(?=\s+Args:|\s+Returns:|\n$)", doc, re.DOTALL)
    result["summary"] = summary_match.group(1).strip() if summary_match else ""

    args_match = re.search(r"Args:\s*((?:.|\n)*?)(?=\n\S|$)", doc)
    if args_match:
        args_text = args_match.group(1)
        arg_pattern = re.compile(
            r"^\s*([\w_]+)\s*\(([\w\[\], ]+)\):\s*(.*?)(?=\n\s*[\w_]+\s*\(|\n*$)",
            re.MULTILINE | re.DOTALL,
        )
        for arg_match in arg_pattern.finditer(args_text):
            name = arg_match.group(1)
            typ = arg_match.group(2)
            desc = arg_match.group(3).strip().replace("\n", " ")
            result["args"].append({"name": name, "type": typ, "description": desc})

    returns_match = re.search(r"Returns:\s*([\w\[\], ]+):\s*(.*)", doc)
    if returns_match:
        result["returns"] = {
            "type": returns_match.group(1).strip(),
            "description": returns_match.group(2).strip(),
        }
    return result


def tools_list(tools: list):
    """Tools list component styled like Agents cards."""
    if not tools:
        me.text(
            "No tools found. Please ensure your MCP server is running and reachable."
        )
        return

    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            gap=18,  # More space between cards
            align_items="center",
            width="100%",
            max_width="900px",
        )
    ):
        for tool in tools:
            with me.box(
                key=f"tool_{tool.name}",
                style=me.Style(
                    background=me.theme_var("surface-container"),
                    border_radius=16,
                    box_shadow="0 2px 8px rgba(0,0,0,0.08)",
                    padding=me.Padding(
                        top="20px", bottom="18px", left="28px", right="28px"
                    ),
                    margin=me.Margin(bottom="7px"),
                    width="100%",
                    max_width="660px",
                ),
            ):
                # Tool name/title
                me.text(
                    getattr(tool, "name", "Unknown Tool"),
                    style=me.Style(
                        font_weight="bold",
                        font_size="1.16rem",
                        color=me.theme_var("on-surface"),
                        margin=me.Margin(bottom="7px"),
                        font_family="inherit",
                    ),
                )
                description = getattr(tool, "description", None)
                parsed = parse_docstring(description) if description else None
                if parsed:
                    if parsed["summary"]:
                        me.text(
                            "Summary",
                            style=me.Style(
                                font_weight="bold",
                                color="#fff",
                                font_size="13.7px",
                                margin=me.Margin(bottom="2px"),
                            ),
                        )
                        me.text(
                            parsed["summary"],
                            style=me.Style(
                                color=me.theme_var("on-surface-variant"),
                                font_size="13.2px",
                                margin=me.Margin(bottom="7px"),
                            ),
                        )
                    # ARGUMENTS
                    if parsed["args"]:
                        me.text(
                            "Arguments",
                            style=me.Style(
                                font_weight="bold",
                                color="#fff",
                                font_size="13.5px",
                                margin=me.Margin(bottom="2px"),
                            ),
                        )
                        for arg in parsed["args"]:
                            me.text(
                                f"• {arg['name']} ({arg['type']}): {arg['description']}",
                                style=me.Style(
                                    color=me.theme_var("on-surface-variant"),
                                    font_size="13.2px",
                                    margin=me.Margin(bottom="0px"),
                                ),
                            )
                    # RETURNS
                    if parsed["returns"]:
                        me.text(
                            "Returns",
                            style=me.Style(
                                font_weight="bold",
                                color="#fff",
                                font_size="13.5px",
                                margin=me.Margin(top="8px", bottom="2px"),
                            ),
                        )
                        me.text(
                            f"{parsed['returns']['type']}: {parsed['returns']['description']}",
                            style=me.Style(
                                color=me.theme_var("on-surface-variant"),
                                font_size="13.2px",
                            ),
                        )
