"""
charon/cli/interactive.py
System Version: v0.1.0 | File Revision: 1.1.0

Module: Interactive terminal UI widgets and choice prompts for Charon CLI.
"""

from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style

from charon.cli.ui import console


async def prompt_concierge_choice(
    proposed_cmd: str, session: Optional[PromptSession] = None
) -> Optional[str]:
    """Presents an interactive selection menu for Concierge proposals with custom entry support."""
    options = [
        ("accept", f"Accept: {proposed_cmd}"),
        ("custom", "Other... (Enter custom prompt)"),
        ("dismiss", "Dismiss proposal"),
        ("exit", "That will be all (Exit)"),
    ]
    selected_index = 0

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        nonlocal selected_index
        selected_index = (selected_index - 1) % len(options)

    @kb.add("down")
    def _(event):
        nonlocal selected_index
        selected_index = (selected_index + 1) % len(options)

    @kb.add("1")
    def _(event):
        event.app.exit(result=options[0][0])

    @kb.add("2")
    def _(event):
        event.app.exit(result=options[1][0])

    @kb.add("3")
    def _(event):
        event.app.exit(result=options[2][0])

    @kb.add("4")
    def _(event):
        event.app.exit(result=options[3][0])

    @kb.add("enter")
    def _(event):
        event.app.exit(result=options[selected_index][0])

    @kb.add("c-c")
    @kb.add("escape")
    def _(event):
        event.app.exit(result="dismiss")

    def get_formatted_text():
        tokens = []
        for i, (action_type, text) in enumerate(options):
            if i == selected_index:
                tokens.append(("class:selected", f" ❯ [{i+1}] {text}\n"))
            else:
                tokens.append(("class:unselected", f"   [{i+1}] {text}\n"))
        return tokens

    style = Style.from_dict({
        "selected": "fg:ansigreen bold",
        "unselected": "fg:ansigray dim",
    })

    layout = Layout(HSplit([Window(content=FormattedTextControl(get_formatted_text))]))

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
    )

    choice = await app.run_async()

    if choice == "accept":
        return proposed_cmd
    elif choice == "custom":
        if session:
            custom_input = await session.prompt_async(
                HTML("<ansigreen><b>Custom Prompt > </b></ansigreen>")
            )
        else:
            custom_input = input("Custom Prompt > ")
        return custom_input.strip() if custom_input else None
    elif choice == "dismiss":
        return None
    elif choice == "exit":
        return "That will be all"

    return None
