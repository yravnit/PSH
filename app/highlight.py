"""
Syntax highlighting and executable discovery for the interactive prompt.

ShellLexer and the executable cache are isolated here. The lexer receives
its known-command sets at construction time and never reads global state.
"""

import os
import sys
import threading

from prompt_toolkit.lexers import Lexer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style


PSH_STYLE = Style.from_dict({
    "builtin": "#50fa7b",          # green
    "command": "#8be9fd",          # cyan
    "unknown_command": "#ff5555",  # red
    "argument": "",                # default terminal color
    "string": "#f1fa8c",           # yellow
    "operator": "#ff79c6",         # pink
    "variable": "#bd93f9",         # purple
})

OPERATORS = {"&&", "||", ";", "|", "&", ">", ">>", "1>", "1>>", "2>", "2>>"}


# ---------------------------------------------------------------------------
# Executable cache
# ---------------------------------------------------------------------------

class ExecutableCache:
    """Scans PATH directories in a background thread.

    complete_commands() never blocks -- it returns whatever is available
    right now and triggers a background scan if the cache is stale.
    """

    def __init__(self):
        self._cache = set()
        self._cached_path = None
        self._lock = threading.Lock()
        self._building = False

    def _scan(self):
        current_path = os.environ.get("PATH", "")
        result = set()
        for directory in current_path.split(os.pathsep):
            if not os.path.isdir(directory):
                continue
            try:
                for entry in os.listdir(directory):
                    full_path = os.path.join(directory, entry)
                    if os.path.isfile(full_path) and (
                        os.access(full_path, os.X_OK) or sys.platform == "win32"
                    ):
                        result.add(entry)
            except OSError:
                pass

        with self._lock:
            self._cache = result
            self._cached_path = current_path
            self._building = False

    def get(self):
        """Return current cached executable set, starting a rebuild if stale."""
        current_path = os.environ.get("PATH", "")
        with self._lock:
            if current_path == self._cached_path:
                return self._cache
            if self._building:
                return self._cache
            # Mark as building inside the lock to avoid the race.
            self._building = True

        thread = threading.Thread(target=self._scan, daemon=True)
        thread.start()
        return self._cache

    def get_all_executables(self):
        """Return all executables from PATH (blocking scan, used for completion)."""
        current_path = os.environ.get("PATH", "")
        result = set()
        for directory in current_path.split(os.pathsep):
            if not os.path.isdir(directory):
                continue
            try:
                for entry in os.listdir(directory):
                    full_path = os.path.join(directory, entry)
                    if os.path.isfile(full_path) and (
                        os.access(full_path, os.X_OK) or sys.platform == "win32"
                    ):
                        result.add(entry)
            except OSError:
                pass
        return result


# ---------------------------------------------------------------------------
# Tokenizer (preserves original characters for display)
# ---------------------------------------------------------------------------

def _tokenize_for_highlight(text):
    """Yield (kind, text) tuples from the raw input string.

    Distinct from parser.parse_command because it preserves quotes,
    whitespace, and operators for colorization rather than stripping them
    for execution.
    """
    tokens = []
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        # Whitespace
        if char == " " or char == "\t":
            start = i
            while i < length and text[i] in (" ", "\t"):
                i += 1
            tokens.append(("whitespace", text[start:i]))
            continue

        # Single-quoted string
        if char == "'":
            start = i
            i += 1
            while i < length and text[i] != "'":
                i += 1
            if i < length:
                i += 1  # closing quote
            tokens.append(("single_quote", text[start:i]))
            continue

        # Double-quoted string
        if char == '"':
            start = i
            i += 1
            while i < length and text[i] != '"':
                if text[i] == "\\" and i + 1 < length:
                    i += 1  # skip escaped char
                i += 1
            if i < length:
                i += 1  # closing quote
            tokens.append(("double_quote", text[start:i]))
            continue

        # Multi-char operators (check before single-char)
        two = text[i:i + 2]
        three = text[i:i + 3]
        if three in ("1>>", "2>>"):
            tokens.append(("operator", three))
            i += 3
            continue
        if two in ("&&", "||", ">>", "1>", "2>"):
            tokens.append(("operator", two))
            i += 2
            continue
        if char in (";", "|", "&", ">"):
            tokens.append(("operator", char))
            i += 1
            continue

        # Variable references
        if char == "$":
            start = i
            if i + 1 < length and text[i + 1] == "{":
                i += 2
                while i < length and text[i] != "}":
                    i += 1
                if i < length:
                    i += 1  # closing brace
                tokens.append(("variable", text[start:i]))
                continue
            else:
                i += 1
                while i < length and (text[i].isalnum() or text[i] in ("_", "?")):
                    i += 1
                tokens.append(("variable", text[start:i]))
                continue

        # Backslash escape
        if char == "\\":
            start = i
            i += 1
            if i < length:
                i += 1
            tokens.append(("word", text[start:i]))
            continue

        # Plain word
        start = i
        while i < length and text[i] not in (" ", "\t", "'", '"', ";", "|", "&", ">", "$", "\\"):
            i += 1
        tokens.append(("word", text[start:i]))

    return tokens


# ---------------------------------------------------------------------------
# Highlighter
# ---------------------------------------------------------------------------

def _highlight_tokens(text, builtin_names, executable_cache):
    """Walk tokens and return (style, text) pairs for prompt_toolkit."""
    spans = []
    tokens = _tokenize_for_highlight(text)
    executables = executable_cache.get()

    expect_command = True

    for kind, value in tokens:
        if kind == "whitespace":
            spans.append(("", value))
            continue

        if kind == "operator":
            spans.append(("class:operator", value))
            if value in ("&&", "||", ";", "|"):
                expect_command = True
            continue

        if kind in ("single_quote", "double_quote"):
            spans.append(("class:string", value))
            if expect_command:
                expect_command = False
            continue

        if kind == "variable":
            spans.append(("class:variable", value))
            if expect_command:
                expect_command = False
            continue

        # kind == "word"
        if expect_command:
            expect_command = False
            if value in builtin_names:
                spans.append(("class:builtin", value))
            elif value in executables:
                spans.append(("class:command", value))
            else:
                spans.append(("class:unknown_command", value))
        else:
            spans.append(("class:argument", value))

    return spans


class ShellLexer(Lexer):
    """prompt_toolkit Lexer that colors the input buffer as the user types."""

    def __init__(self, builtin_names, executable_cache):
        self._builtin_names = builtin_names
        self._executable_cache = executable_cache

    def lex_document(self, document):
        line_text = document.text

        def get_line(lineno):
            if lineno != 0:
                return FormattedText([])
            return FormattedText(
                _highlight_tokens(line_text, self._builtin_names, self._executable_cache)
            )

        return get_line
