try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None
import subprocess
import sys
import os
import re
import io
import threading
from io import StringIO

from prompt_toolkit import PromptSession
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory


jobs = []
history = []
variables = {}
history_cursor = 0
last_exit_status = 0

VAR_PATTERN = re.compile(
    r'\$\{([A-Za-z_][A-Za-z0-9_]*|\?)\}|\$([A-Za-z_][A-Za-z0-9_]*|\?)'
)


def has_fileno(stream):
    if stream is None:
        return False
    try:
        stream.fileno()
        return True
    except (AttributeError, io.UnsupportedOperation, OSError):
        return False


def find_executable_path(target):
    if os.path.isfile(target) and (os.access(target, os.X_OK) or sys.platform == "win32"):
        return target

    path_env = os.environ.get("PATH", "")

    for directory in path_env.split(os.pathsep):
        full_path = os.path.join(directory, target)

        if os.path.isfile(full_path) and (os.access(full_path, os.X_OK) or sys.platform == "win32"):
            return full_path

    return None


def parse_command(line):
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


def write_output(output, stdout_stream):
    stdout_stream.write(output)
    stdout_stream.flush()


def write_error(error, stderr_stream):
    stderr_stream.write(error)
    stderr_stream.flush()


def completer(text, state):
    line = readline.get_line_buffer()

    if " " not in line:
        matches = complete_commands(text)
    else:
        matches = complete_filenames(text)

    if state < len(matches):
        return matches[state]

    return None


def get_executables():
    executables = set()
    path_env = os.environ.get("PATH", "")

    for directory in path_env.split(os.pathsep):
        if not os.path.isdir(directory):
            continue

        try:
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)

                if (
                    os.path.isfile(full_path)
                    and (os.access(full_path, os.X_OK) or sys.platform == "win32")
                ):
                    executables.add(entry)
        except OSError:
            pass

    return executables


def complete_commands(text):
    commands = set(BUILTIN_HANDLERS)
    commands.update(get_executables())

    return sorted(
        command + " "
        for command in commands
        if command.startswith(text)
    )


def complete_filenames(text):
    matches = []

    if "/" in text:
        directory, prefix = text.rsplit("/", 1)

        try:
            for entry in os.listdir(directory):
                if entry.startswith(prefix):
                    full_path = os.path.join(directory, entry)

                    if os.path.isdir(full_path):
                        matches.append(f"{directory}/{entry}/")
                    else:
                        matches.append(f"{directory}/{entry} ")
        except OSError:
            pass
    else:
        for entry in os.listdir("."):
            if entry.startswith(text):
                if os.path.isdir(entry):
                    matches.append(entry + "/")
                else:
                    matches.append(entry + " ")

    return sorted(matches)


def reap_jobs(stdout_stream):
    jobs_to_remove = []

    for index, job in enumerate(jobs):
        if job["process"].poll() is None:
            continue

        if index == len(jobs) - 1:
            marker = "+"
        elif index == len(jobs) - 2:
            marker = "-"
        else:
            marker = " "

        command_text = job["command"].removesuffix(" &")

        output = (
            f"[{job['job_id']}]{marker}  "
            f"{'Done':<24}"
            f"{command_text}\n"
        )

        write_output(output, stdout_stream)
        jobs_to_remove.append(job)

    for job in jobs_to_remove:
        jobs.remove(job)


if readline:
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" \t\n")


def split_pipeline(parts):
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


def run_pipeline(commands, stdout_stream=sys.stdout, stderr_stream=sys.stderr):
    processes = []
    previous_pipe = None
    last_exit_code = 0
    last_process_to_capture = None

    for index, command in enumerate(commands):
        last_command = (index == len(commands) - 1)

        # BUILTIN
        if is_builtin(command[0]):
            if previous_pipe:
                previous_pipe.close()
                previous_pipe = None

            buffer = StringIO()
            ret = BUILTIN_HANDLERS[command[0]](
                command,
                buffer,
                stderr_stream
            )
            output = buffer.getvalue().encode()

            if last_command:
                last_exit_code = ret if ret is not None else 0
                if hasattr(stdout_stream, "buffer"):
                    stdout_stream.buffer.write(output)
                    stdout_stream.flush()
                else:
                    stdout_stream.write(output.decode())
                    stdout_stream.flush()
            else:
                read_end, write_end = os.pipe()
                os.write(write_end, output)
                os.close(write_end)
                previous_pipe = os.fdopen(read_end, "rb")

        # EXTERNAL
        else:
            capture_last = False
            if last_command:
                if stdout_stream is sys.stdout or stdout_stream is None:
                    stdout_target = None
                elif has_fileno(stdout_stream):
                    stdout_target = stdout_stream
                else:
                    stdout_target = subprocess.PIPE
                    capture_last = True
            else:
                stdout_target = subprocess.PIPE

            stderr_target = stderr_stream if has_fileno(stderr_stream) else None

            executable = find_executable_path(command[0])
            if not executable:
                write_error(f"{command[0]}: command not found\n", stderr_stream)
                last_exit_code = 127
                if previous_pipe:
                    previous_pipe.close()
                    previous_pipe = None
                continue

            try:
                process = subprocess.Popen(
                    command,
                    stdin=previous_pipe,
                    stdout=stdout_target,
                    stderr=stderr_target
                )
            except Exception as e:
                write_error(f"{command[0]}: {e}\n", stderr_stream)
                last_exit_code = 1
                if previous_pipe:
                    previous_pipe.close()
                    previous_pipe = None
                continue

            if previous_pipe:
                previous_pipe.close()
                previous_pipe = None

            if not last_command:
                previous_pipe = process.stdout
            elif capture_last:
                last_process_to_capture = process

            processes.append(process)

    for process in processes:
        code = process.wait()
        last_exit_code = code

    if previous_pipe:
        previous_pipe.close()
        previous_pipe = None

    if last_process_to_capture and last_process_to_capture.stdout:
        out_bytes = last_process_to_capture.stdout.read()
        last_process_to_capture.stdout.close()
        stdout_stream.write(out_bytes.decode(errors="replace"))
        stdout_stream.flush()

    return last_exit_code


def run_builtin_capture(parts):
    buffer = StringIO()

    BUILTIN_HANDLERS[parts[0]](
        parts,
        buffer,
        sys.stderr
    )

    return buffer.getvalue().encode()


def builtin_echo(parts, stdout_stream, stderr_stream):
    write_output(
        " ".join(parts[1:]) + '\n',
        stdout_stream
    )
    return 0


def builtin_pwd(parts, stdout_stream, stderr_stream):
    write_output(
        os.getcwd() + "\n",
        stdout_stream
    )
    return 0


def builtin_type(parts, stdout_stream, stderr_stream):
    if len(parts) < 2:
        return 1

    exit_code = 0
    for target in parts[1:]:
        if target in BUILTIN_HANDLERS:
            output = f"{target} is a shell builtin\n"
        else:
            executable_path = find_executable_path(target)
            if executable_path:
                output = f"{target} is {executable_path}\n"
            else:
                output = f"{target}: not found\n"
                exit_code = 1

        write_output(output, stdout_stream)

    return exit_code


def builtin_cd(parts, stdout_stream, stderr_stream):
    if len(parts) < 2:
        path = os.environ.get("HOME", "")
    else:
        path = parts[1]

    if path == "~":
        path = os.environ.get("HOME", "")

    try:
        os.chdir(path)
        return 0
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        write_error(
            f"cd: {path}: No such file or directory\n",
            stderr_stream
        )
        return 1


def builtin_jobs(parts, stdout_stream, stderr_stream):
    jobs_to_remove = []

    for index, job in enumerate(jobs):
        if index == len(jobs) - 1:
            marker = "+"
        elif index == len(jobs) - 2:
            marker = "-"
        else:
            marker = " "

        if job["process"].poll() is None:
            status = "Running"
            command_text = job["command"]
        else:
            status = "Done"
            command_text = job["command"].removesuffix(" &")
            jobs_to_remove.append(job)

        output = (
            f"[{job['job_id']}]{marker}  "
            f"{status:<24}"
            f"{command_text}\n"
        )

        write_output(output, stdout_stream)

    for job in jobs_to_remove:
        jobs.remove(job)

    return 0


def builtin_exit(parts, stdout_stream, stderr_stream):
    save_history_on_exit()
    code = 0
    if len(parts) > 1:
        try:
            code = int(parts[1])
        except ValueError:
            code = 1
    sys.exit(code)


def builtin_history(parts, stdout_stream, stderr_stream):
    if len(parts) == 3:
        flag = parts[1]
        path = parts[2]

        try:
            if flag == "-r":
                history_read(path)
                return 0
            if flag == "-w":
                history_write(path)
                return 0
            if flag == "-a":
                history_append(path)
                return 0
        except OSError:
            return 1

    if len(parts) > 1:
        try:
            limit = int(parts[1])
            start_index = max(0, len(history) - limit)
            entries = history[start_index:]
        except ValueError:
            write_error(f"history: {parts[1]}: numeric argument required\n", stderr_stream)
            return 1
    else:
        start_index = 0
        entries = history

    for index, command in enumerate(
        entries,
        start=start_index + 1
    ):
        write_output(
            f"    {index}  {command}\n",
            stdout_stream
        )

    return 0


def history_read(path):
    global history_cursor

    with open(path, "r") as file:
        for line in file:
            command = line.rstrip("\n")
            if command:
                history.append(command)

    history_cursor = len(history)


def history_write(path):
    global history_cursor

    with open(path, "w") as file:
        for command in history:
            file.write(command + "\n")

    history_cursor = len(history)


def history_append(path):
    global history_cursor

    with open(path, "a") as file:
        for command in history[history_cursor:]:
            file.write(command + "\n")

    history_cursor = len(history)


def load_history_on_startup():
    histfile = os.environ.get("HISTFILE")

    if not histfile:
        return

    try:
        history_read(histfile)
    except OSError:
        pass


def save_history_on_exit():
    histfile = os.environ.get("HISTFILE")

    if not histfile:
        return

    try:
        history_write(histfile)
    except OSError:
        pass


def builtin_declare(parts, stdout_stream, stderr_stream):
    # declare -p NAME
    if len(parts) == 3 and parts[1] == "-p":
        name = parts[2]

        if name in variables:
            write_output(
                f'declare -- {name}="{variables[name]}"\n',
                stdout_stream
            )
            return 0
        else:
            write_error(
                f"declare: {name}: not found\n",
                stderr_stream
            )
            return 1

    # declare NAME=value
    if len(parts) == 2 and "=" in parts[1]:
        name, value = parts[1].split("=", 1)

        if not is_valid_identifier(name):
            write_error(
                f"declare: `{parts[1]}': not a valid identifier\n",
                stderr_stream
            )
            return 1

        variables[name] = value
        return 0

    return 0


def builtin_true(parts, stdout_stream, stderr_stream):
    return 0


def builtin_false(parts, stdout_stream, stderr_stream):
    return 1


def is_valid_identifier(name):
    if not name:
        return False

    if not (name[0].isalpha() or name[0] == "_"):
        return False

    return all(c.isalnum() or c == "_" for c in name)


def expand_variables(parts):
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

        # Drop arguments that became empty
        if part != "":
            expanded.append(part)

    return expanded


BUILTIN_HANDLERS = {
    "echo": builtin_echo,
    "pwd": builtin_pwd,
    "type": builtin_type,
    "cd": builtin_cd,
    "jobs": builtin_jobs,
    "history": builtin_history,
    "exit": builtin_exit,
    "declare": builtin_declare,
    "true": builtin_true,
    "false": builtin_false,
}


def is_builtin(command):
    return command in BUILTIN_HANDLERS


_executable_cache = set()
_executable_cache_path = None
_executable_cache_lock = threading.Lock()
_executable_cache_building = False


def _build_executable_cache():
    """Scan PATH directories in a background thread."""
    global _executable_cache, _executable_cache_path, _executable_cache_building
    current_path = os.environ.get("PATH", "")
    result = get_executables()
    with _executable_cache_lock:
        _executable_cache = result
        _executable_cache_path = current_path
        _executable_cache_building = False


def _cached_executables():
    """Return the cached set of executable names.

    If the cache is stale or empty, kicks off a background rebuild and
    returns whatever is available right now (possibly empty). The prompt
    never blocks.
    """
    global _executable_cache_building
    current_path = os.environ.get("PATH", "")
    with _executable_cache_lock:
        if current_path == _executable_cache_path:
            return _executable_cache
        if _executable_cache_building:
            return _executable_cache
    _executable_cache_building = True
    thread = threading.Thread(target=_build_executable_cache, daemon=True)
    thread.start()
    return _executable_cache


OPERATORS = {"&&", "||", ";", "|", "&", ">", ">>", "1>", "1>>", "2>", "2>>"}


class ShellLexer(Lexer):
    """Tokenizes the input buffer and returns colored spans for prompt_toolkit."""

    def lex_document(self, document):
        line_text = document.text

        def get_line(lineno):
            if lineno != 0:
                return FormattedText([])
            return FormattedText(_highlight_tokens(line_text))

        return get_line


def _highlight_tokens(text):
    """Walk the input character by character and produce (style, text) pairs."""
    spans = []
    tokens = _tokenize_for_highlight(text)

    seen_command = False
    expect_command = True  # next non-operator token is a command

    for kind, value in tokens:
        if kind == "whitespace":
            spans.append(("", value))
            continue

        if kind == "operator":
            spans.append(("class:operator", value))
            # After a pipe or chain operator, the next word is a new command.
            if value in ("&&", "||", ";", "|"):
                expect_command = True
                seen_command = False
            continue

        if kind == "single_quote" or kind == "double_quote":
            spans.append(("class:string", value))
            # A quoted token in command position counts as the command.
            if expect_command:
                expect_command = False
                seen_command = True
            continue

        if kind == "variable":
            spans.append(("class:variable", value))
            if expect_command:
                expect_command = False
                seen_command = True
            continue

        # kind == "word"
        if expect_command:
            expect_command = False
            seen_command = True
            if value in BUILTIN_HANDLERS:
                spans.append(("class:builtin", value))
            elif value in _cached_executables():
                spans.append(("class:command", value))
            else:
                spans.append(("class:unknown_command", value))
        else:
            spans.append(("class:argument", value))

    return spans


def _tokenize_for_highlight(text):
    """Yield (kind, text) tuples from the raw input string.

    This is separate from parse_command because it needs to preserve the
    original characters (quotes, whitespace, operators) for display rather
    than stripping them for execution.
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


PSH_STYLE = Style.from_dict({
    "builtin": "#50fa7b",          # green
    "command": "#8be9fd",          # cyan
    "unknown_command": "#ff5555",  # red
    "argument": "",                # default terminal color
    "string": "#f1fa8c",           # yellow
    "operator": "#ff79c6",         # pink
    "variable": "#bd93f9",         # purple
})


def execute_pipeline_or_command(parts, default_stdout=sys.stdout, default_stderr=sys.stderr):
    if not parts:
        return 0

    background = False
    if parts and parts[-1] == "&":
        background = True
        parts = parts[:-1]

    if not parts:
        return 0

    parts, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
    parts = expand_variables(parts)

    if not parts:
        return 0

    stdout_stream = default_stdout
    stderr_stream = default_stderr
    opened_streams = []

    try:
        if stdout_file:
            mode = "a" if append_stdout else "w"
            stdout_stream = open(stdout_file, mode, encoding="utf-8")
            opened_streams.append(stdout_stream)

        if stderr_file:
            mode = "a" if append_stderr else "w"
            stderr_stream = open(stderr_file, mode, encoding="utf-8")
            opened_streams.append(stderr_stream)

        if "|" in parts:
            commands = split_pipeline(parts)
            return run_pipeline(commands, stdout_stream, stderr_stream)

        command = parts[0]

        if is_builtin(command):
            code = BUILTIN_HANDLERS[command](
                parts,
                stdout_stream,
                stderr_stream
            )
            return code if code is not None else 0

        executable_path = find_executable_path(command)
        if executable_path:
            if background:
                stdout_target = stdout_stream if has_fileno(stdout_stream) else None
                stderr_target = stderr_stream if has_fileno(stderr_stream) else None
                process = subprocess.Popen(
                    parts,
                    stdout=stdout_target,
                    stderr=stderr_target
                )
                jobs.append({
                    "job_id": len(jobs) + 1,
                    "pid": process.pid,
                    "command": " ".join(parts) + " &",
                    "process": process
                })
                write_output(
                    f"[{len(jobs)}] {process.pid}\n",
                    stdout_stream
                )
                return 0
            else:
                if has_fileno(stdout_stream) and has_fileno(stderr_stream):
                    res = subprocess.run(
                        parts,
                        stdout=stdout_stream,
                        stderr=stderr_stream
                    )
                else:
                    res = subprocess.run(
                        parts,
                        stdout=subprocess.PIPE if not has_fileno(stdout_stream) else stdout_stream,
                        stderr=subprocess.PIPE if not has_fileno(stderr_stream) else stderr_stream
                    )
                    if not has_fileno(stdout_stream) and res.stdout:
                        stdout_stream.write(res.stdout.decode(errors="replace"))
                        stdout_stream.flush()
                    if not has_fileno(stderr_stream) and res.stderr:
                        stderr_stream.write(res.stderr.decode(errors="replace"))
                        stderr_stream.flush()
                return res.returncode
        else:
            write_error(
                f"{command}: command not found\n",
                stderr_stream
            )
            return 127
    except Exception as e:
        write_error(f"shell: {e}\n", stderr_stream)
        return 1
    finally:
        for stream in opened_streams:
            stream.close()


def execute_line(line, stdout_stream=sys.stdout, stderr_stream=sys.stderr):
    global last_exit_status

    parts = parse_command(line)
    if not parts:
        return last_exit_status

    chains = split_command_chains(parts)

    for op, cmd_tokens in chains:
        if not cmd_tokens:
            continue

        if op is None or op == ";":
            last_exit_status = execute_pipeline_or_command(
                cmd_tokens,
                stdout_stream,
                stderr_stream
            )
        elif op == "&&":
            if last_exit_status == 0:
                last_exit_status = execute_pipeline_or_command(
                    cmd_tokens,
                    stdout_stream,
                    stderr_stream
                )
        elif op == "||":
            if last_exit_status != 0:
                last_exit_status = execute_pipeline_or_command(
                    cmd_tokens,
                    stdout_stream,
                    stderr_stream
                )

    return last_exit_status


def main():
    global last_exit_status

    pt_history = InMemoryHistory()
    session = PromptSession(
        lexer=ShellLexer(),
        style=PSH_STYLE,
        history=pt_history,
    )

    while True:
        reap_jobs(sys.stdout)

        try:
            line = session.prompt("$ ")
        except EOFError:
            break
        except KeyboardInterrupt:
            continue

        if line.strip():
            history.append(line)

        execute_line(line, sys.stdout, sys.stderr)


if __name__ == "__main__":
    load_history_on_startup()
    main()