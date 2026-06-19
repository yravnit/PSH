import readline
import subprocess
import sys
import os
from io import StringIO

jobs = []
history = []
history_cursor = 0

def find_executable_path(target):
    path_env = os.environ.get("PATH", "")

    for directory in path_env.split(os.pathsep):
        full_path = os.path.join(directory, target)

        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
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

        # signle quotes mode
        if char == "'" and not in_double_quotes:
            in_single_quotes = not in_single_quotes

        # double quotes mode
        elif char == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes

        # backslash outisde quotes
        elif char == "\\" and not in_single_quotes and not in_double_quotes:
            i += 1

            if i < len(line):
                current.append(line[i])

        # backslash inside double quotes
        elif char == "\\" and in_double_quotes:
            if i + 1 < len(line) and line[i + 1] in ['\\', '"']:
                i += 1
                current.append(line[i])
            else:
                current.append(char)

        # token seperator
        elif char == " " and not in_single_quotes and not in_double_quotes:
            if current:
                parts.append("".join(current))
                current = []

        # normal charachter
        else:
            current.append(char)

        i += 1

    if current:
        parts.append("".join(current))

    return parts

def extract_redirection(parts):
    stdout_file = None
    stderr_file = None

    append_stdout = False
    append_stderr = False

    cleaned_parts = []

    i = 0

    while i < len(parts):
        if parts[i] in [">", "1>"]:
            stdout_file = parts[i + 1]
            i += 2

        elif parts[i] in [">>", "1>>"]:
            stdout_file = parts[i + 1]
            append_stdout = True
            i += 2

        elif parts[i] == "2>":
            stderr_file = parts[i + 1]
            i += 2

        elif parts[i] == "2>>":
            stderr_file = parts[i + 1]
            append_stderr = True
            i += 2

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
                    and os.access(full_path, os.X_OK)
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

def run_pipeline(commands):

    processes = []

    previous_pipe = None

    for index, command in enumerate(commands):

        last_command = (
            index == len(commands) - 1
        )

        # BUILTIN
        if is_builtin(command[0]):

            if previous_pipe:
                previous_pipe.close()

            output = run_builtin_capture(
                command
            )

            if last_command:

                sys.stdout.buffer.write(
                    output
                )
                sys.stdout.flush()

            else:

                read_end, write_end = os.pipe()

                os.write(
                    write_end,
                    output
                )

                os.close(write_end)

                previous_pipe = os.fdopen(
                    read_end,
                    "rb"
                )

        # EXTERNAL
        else:

            stdout_target = (
                None
                if last_command
                else subprocess.PIPE
            )

            process = subprocess.Popen(
                command,
                stdin=previous_pipe,
                stdout=stdout_target
            )

            if previous_pipe:
                previous_pipe.close()

            if not last_command:
                previous_pipe = (
                    process.stdout
                )

            processes.append(
                process
            )

    for process in processes:
        process.wait()

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

def builtin_pwd(parts, stdout_stream, stderr_stream):
    write_output(
        os.getcwd() + "\n",
        stdout_stream
    )

def builtin_type(parts, stdout_stream, stderr_stream):

    if len(parts) < 2:
        return

    target = parts[1]

    if target in BUILTIN_HANDLERS:
        output = f"{target} is a shell builtin\n"
    else:
        executable_path = find_executable_path(target)

        if executable_path:
            output = f"{target} is {executable_path}\n"
        else:
            output = f"{target}: not found\n"

    write_output(output, stdout_stream)

def builtin_cd(parts, stdout_stream, stderr_stream):

    if len(parts) < 2:
        path = os.environ.get("HOME", "")
    else:
        path = parts[1]

    if path == "~":
        path = os.environ.get("HOME", "")


    try:
        os.chdir(path)
    except FileNotFoundError:
        write_error(
            f"cd: {path}: No such file or directory\n",
            stderr_stream
        )

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

def builtin_exit(parts, stdout_stream, stderr_stream):
    sys.exit(0)

def builtin_history(parts, stdout_stream, stderr_stream):

    if len(parts) == 3:

        flag = parts[1]
        path = parts[2]

        try:
            if flag == "-r":
                history_read(path)
                return

            if flag == "-w":
                history_write(path)
                return

            if flag == "-a":
                history_append(path)
                return

        except OSError:
            return

    # history <n>
    if len(parts) > 1:

        try:
            limit = int(parts[1])

            start_index = max(
                0,
                len(history) - limit
            )

            entries = history[start_index:]

        except ValueError:
            return

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

BUILTIN_HANDLERS = {
    "echo": builtin_echo,
    "pwd": builtin_pwd,
    "type": builtin_type,
    "cd": builtin_cd,
    "jobs": builtin_jobs,
    "history": builtin_history,
    "exit": builtin_exit,
}

def is_builtin(command):
    return command in BUILTIN_HANDLERS

def main():
    while True:
        
        reap_jobs(sys.stdout)

        try:
            line = input("$ ")
        except EOFError:
            break

        if line.strip():
            history.append(line)
        
        original_command = line

        parts = parse_command(line)

        background = False

        if parts and parts[-1] == "&":
            background = True
            parts.pop()

        parts, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)

        stdout_stream = sys.stdout
        stderr_stream = sys.stderr

        opened_streams = []
        try:
            if stdout_file:
                mode = "a" if append_stdout else "w"
                stdout_stream = open(stdout_file, mode)
                opened_streams.append(stdout_stream)
            
            if stderr_file:
                mode = "a" if append_stderr else "w"
                stderr_stream = open(stderr_file, mode)
                opened_streams.append(stderr_stream)

            # Empty input
            if len(parts) == 0:
                continue

            if "|"  in parts:

                commands = split_pipeline(parts)

                run_pipeline(commands)

                continue

            command = parts[0] # first part of the line is the command

            if is_builtin(command):

                BUILTIN_HANDLERS[command](
                    parts,
                    stdout_stream,
                    stderr_stream
                )

            # unknown command
            else:
                executable_path = find_executable_path(command)

                if executable_path:
                    if background:
                        process = subprocess.Popen(parts)

                        jobs.append({
                            "job_id": len(jobs) + 1,
                            "pid": process.pid,
                            "command": original_command,
                            "process": process
                        })

                        write_output(
                            f"[{len(jobs)}] {process.pid}\n",
                            stdout_stream
                        )
                    else:
                        subprocess.run(
                            parts,
                            stdout=stdout_stream,
                            stderr=stderr_stream
                        )
                else:
                    write_error(
                        f"{command}: command not found\n",
                        stderr_stream
                    )
        finally:
            for stream in opened_streams:
                stream.close()
if __name__ == "__main__":
    load_history_on_startup()
    main()