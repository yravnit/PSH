"""
Shell tokenizer, parser, and variable expansion.

All functions here are pure -- no global state is read or written.
"""

import re

VAR_PATTERN = re.compile(
    r'\$\{([A-Za-z_][A-Za-z0-9_]*|\?)\}|\$([A-Za-z_][A-Za-z0-9_]*|\?)'
)


def parse_command(line):
    """Tokenize a raw input line into parts.

    Handles single quotes, double quotes, backslash escapes, and control
    operators. Returns a flat list of tokens and operator strings.
    """
    parts = []
    current = []

    in_single_quotes = False
    in_double_quotes = False

    i = 0

    while i < len(line):
        char = line[i]

        # single quotes mode
        if char == "'" and not in_double_quotes:
            in_single_quotes = not in_single_quotes
            i += 1
            continue

        # double quotes mode
        if char == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes
            i += 1
            continue

        # backslash outside quotes
        if char == "\\" and not in_single_quotes and not in_double_quotes:
            i += 1
            if i < len(line):
                current.append(line[i])
            i += 1
            continue

        # backslash inside double quotes
        if char == "\\" and in_double_quotes:
            if i + 1 < len(line) and line[i + 1] in ['\\', '"', '$']:
                i += 1
                current.append(line[i])
            else:
                current.append(char)
            i += 1
            continue

        # operator and separator handling outside quotes
        if not in_single_quotes and not in_double_quotes:
            if line[i:i + 2] in ("&&", "||"):
                if current:
                    parts.append("".join(current))
                    current = []
                parts.append(line[i:i + 2])
                i += 2
                continue

            if not current and line[i:i + 3] in ("1>>", "2>>"):
                parts.append(line[i:i + 3])
                i += 3
                continue

            if not current and line[i:i + 2] in ("1>", "2>"):
                parts.append(line[i:i + 2])
                i += 2
                continue

            if line[i:i + 2] == ">>":
                if current:
                    parts.append("".join(current))
                    current = []
                parts.append(">>")
                i += 2
                continue

            if char in (";", "|", "&", ">"):
                if current:
                    parts.append("".join(current))
                    current = []
                parts.append(char)
                i += 1
                continue

            if char == " ":
                if current:
                    parts.append("".join(current))
                    current = []
                i += 1
                continue

        current.append(char)
        i += 1

    if current:
        parts.append("".join(current))

    return parts


def split_command_chains(parts):
    """Split a flat token list into a list of (operator, tokens) tuples.

    The operator is None for the first command and one of '&&', '||', ';'
    for subsequent commands.
    """
    chains = []
    current = []
    current_op = None

    for token in parts:
        if token in ("&&", "||", ";"):
            if current or current_op is not None:
                chains.append((current_op, current))
                current = []
            current_op = token
        elif token == "&":
            current.append(token)
            chains.append((current_op, current))
            current = []
            current_op = None
        else:
            current.append(token)

    if current or current_op is not None:
        chains.append((current_op, current))

    return chains


def extract_redirection(parts):
    """Pull redirection tokens out of a token list.

    Returns (cleaned_parts, stdout_file, stderr_file, append_stdout, append_stderr).
    """
    stdout_file = None
    stderr_file = None

    append_stdout = False
    append_stderr = False

    cleaned_parts = []

    i = 0

    while i < len(parts):
        if parts[i] in [">", "1>"]:
            if i + 1 < len(parts):
                stdout_file = parts[i + 1]
                i += 2
            else:
                i += 1

        elif parts[i] in [">>", "1>>"]:
            if i + 1 < len(parts):
                stdout_file = parts[i + 1]
                append_stdout = True
                i += 2
            else:
                i += 1

        elif parts[i] == "2>":
            if i + 1 < len(parts):
                stderr_file = parts[i + 1]
                i += 2
            else:
                i += 1

        elif parts[i] == "2>>":
            if i + 1 < len(parts):
                stderr_file = parts[i + 1]
                append_stderr = True
                i += 2
            else:
                i += 1

        else:
            cleaned_parts.append(parts[i])
            i += 1

    return cleaned_parts, stdout_file, stderr_file, append_stdout, append_stderr


def split_pipeline(parts):
    """Split a token list on '|' into a list of per-stage token lists."""
    commands = []
    current = []

    for token in parts:
        if token == "|":
            commands.append(current)
            current = []
        else:
            current.append(token)

    commands.append(current)
    return commands


def expand_variables(parts, variables, last_exit_status):
    """Expand $VAR and ${VAR} references in each token.

    Args:
        parts: token list to expand.
        variables: dict of shell-local variables.
        last_exit_status: current value of $?.

    Returns a new list with variables resolved. Tokens that expand to an
    empty string are dropped (matching POSIX unquoted-expansion behaviour).
    """
    import os

    expanded = []

    for part in parts:
        def replace_var(m):
            var_name = m.group(1) or m.group(2)
            if var_name == "?":
                return str(last_exit_status)
            if var_name in variables:
                return variables[var_name]
            return os.environ.get(var_name, "")

        part = VAR_PATTERN.sub(replace_var, part)

        if part != "":
            expanded.append(part)

    return expanded
