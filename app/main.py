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

    for char in line:
        # Toggle quote mode
        if char == "'":
            in_single_quotes = not in_single_quotes

        # Token separator only outside quotes
        elif char == " " and not in_single_quotes:
            if current:
                parts.append("".join(current))
                current = []

        # Normal character
        else:
            current.append(char)

    # Final token
    if current:
        parts.append("".join(current))

    return parts

def main():
    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()

        line = sys.stdin.readline()

        if  not line:
            break

        line = line.rstrip("\n")
        parts = parse_command(line)

        # Empty input
        if len(parts) == 0:
            continue

        command = parts[0] # first part of the line is the command

        # exit
        if command == "exit":
            break

        # echo
        elif command == "echo":
            sys.stdout.write(" ".join(parts[1:]) + "\n")
            sys.stdout.flush()
        
        # pwd
        elif command == "pwd":
            sys.stdout.write(os.getcwd() + "\n")
            sys.stdout.flush()

        # cd
        elif command == "cd":
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
            target = parts[1]

            if target in BUILTINS:
                sys.stdout.write(f"{target} is a shell builtin\n")
            else:
                executable_path = find_executable_path(target)

                if executable_path:
                    sys.stdout.write(f"{target} is {executable_path}\n")
                else:
                    sys.stdout.write(f"{target}: not found\n")

            sys.stdout.flush()

        # unknown command
        else:
            executable_path = find_executable_path(command)

            if executable_path:
                subprocess.run(parts)
            else:
                sys.stdout.write(f"{command}: command not found\n")
                sys.stdout.flush()

if __name__ == "__main__":
    main()