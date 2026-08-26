"""
PSH -- interactive REPL entry point.

Wires together the parser, executor, builtins, and highlighter.
All mutable shell state lives in a single ShellContext instance created
here and passed through to every subsystem.
"""

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from app.builtins import ShellContext, load_history_on_startup, get_builtin_names
from app.executor import execute_line, reap_jobs
from app.highlight import ExecutableCache, ShellLexer, PSH_STYLE


def main():
    ctx = ShellContext()
    load_history_on_startup(ctx)

    executable_cache = ExecutableCache()
    builtin_names = get_builtin_names()

    # Use a single prompt_toolkit history so arrow-up and the history builtin
    # stay in sync. Each line is appended to both ctx.history (for the history
    # command) and to the PromptSession history (for arrow-up recall).
    pt_history = InMemoryHistory()

    session = PromptSession(
        lexer=ShellLexer(builtin_names, executable_cache),
        style=PSH_STYLE,
        history=pt_history,
    )

    while True:
        reap_jobs(ctx, sys.stdout)

        try:
            line = session.prompt("$ ")
        except EOFError:
            break
        except KeyboardInterrupt:
            continue

        if line.strip():
            ctx.history.append(line)

        execute_line(line, ctx, sys.stdout, sys.stderr)


if __name__ == "__main__":
    main()