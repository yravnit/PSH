import readline
import subprocess
import sys
import os

BUILTINS = ["echo", "exit", "type", "pwd", "cd", "jobs"]

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

    commands = set(BUILTINS)
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
    
readline.set_completer(completer)
readline.parse_and_bind("tab: complete")
readline.set_completer_delims(" \t\n")

def main():
    while True:
        
        try:
            line = input("$ ")
        except EOFError:
            break

        parts = parse_command(line)

        background = False

        if parts and parts[-1] ==  "&":
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

            command = parts[0] # first part of the line is the command

            # exit
            if command == "exit":
                break

            # echo
            elif command == "echo":
                output = " ".join(parts[1:]) + "\n"
                write_output(output, stdout_stream)
            
            # pwd
            elif command == "pwd":
                output = os.getcwd() + "\n"
                write_output(output, stdout_stream)

            # cd
            elif command == "cd":

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

            # type
            elif command == "type":
                if len(parts) < 2:
                    continue

                target = parts[1]

                if target in BUILTINS:
                    output = f"{target} is a shell builtin\n"
                else:
                    executable_path = find_executable_path(target)

                    if executable_path:
                        output = f"{target} is {executable_path}\n"
                    else:
                        output = f"{target}: not found\n"

                write_output(output, stdout_stream)


            # jobs
            elif command == "jobs":
                pass
            
            # unknown command
            else:
                executable_path = find_executable_path(command)

                if executable_path:
                    if background:
                        process = subprocess.Popen(
                            parts,
                            stdout=stdout_stream,
                            stderr=stderr_stream
                        )

                        write_output(
                            f"[1] {process.pid}\n",
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
    main()