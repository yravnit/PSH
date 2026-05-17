import sys


def main():
    builtins = ["echo", "exit", "type"]

    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()

        line = sys.stdin.readline()

        if  not line:
            break

        line = line.rstrip("\n")
        parts = line.split()

        # Empty input
        if len(parts) == 0:
            continue

        command = parts[0]

        # exit
        if command == "exit":
            break

        # echo
        elif command == "echo":
            sys.stdout.write(" ".join(parts[1:]) + "\n")
            sys.stdout.flush()
        
        # type
        elif command == "type":
            target = parts[1]

            if target in builtins:
                sys.stdout.write(f"{target} is a shell builtin\n")
            else:
                sys.stdout.write(f"{target}: not found\n")

            sys.stdout.flush()

        # unknown command
        else:
            sys.stdout.write(f"{command}: command not found\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()