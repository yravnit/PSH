import subprocess
import sys
import os

BUILTINS = ["echo", "exit", "type", "pwd", "cd"]

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
    cleaned_parts = []

    i = 0

    while i < len(parts):
        if parts[i] in [">", "1>"]:
            stdout_file = parts[i + 1]
            i += 2
        else:
            cleaned_parts.append(parts[i])
            i += 1

    return cleaned_parts, stdout_file


def write_output(output, stdout_file):
    if stdout_file:
        with open(stdout_file, "w") as f:
            f.write(output)
    else:
        sys.stdout.write(output)
        sys.stdout.flush()

def main():
    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()

        line = sys.stdin.readline()

        if  not line:
            break

        line = line.rstrip("\n")
        parts = parse_command(line)

        parts, stdout_file = extract_redirection(parts)

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
            write_output(output, stdout_file)
        
        # pwd
        elif command == "pwd":
            output = os.getcwd() + "\n"
            write_output(output, stdout_file)

        # cd
        elif command == "cd":

            if len(parts) < 2:
                os.environ.get("HOME", "")
            path = parts[1]

            if path == "~":
                path = os.environ.get("HOME", "")


            try:
                os.chdir(path)
            except FileNotFoundError:
                sys.stdout.write(f"cd: {path}: No such file or directory\n")
                sys.stdout.flush()

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

            write_output(output, stdout_file)

        # unknown command
        else:
            executable_path = find_executable_path(command)

            if executable_path:
                if stdout_file:
                    with open(stdout_file, "w") as f:
                        subprocess.run(parts, stdout=f)
                else:
                    subprocess.run(parts)
            else:
                sys.stdout.write(f"{command}: command not found\n")
                sys.stdout.flush()

if __name__ == "__main__":
    main()