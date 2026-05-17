import sys


def main():
    while True:
        sys.stdout.write("$ ")
        sys.stdout.flush()

        command = sys.stdin.readline().rstrip("\n")
        if command == "exit":
            break
        if command.startswith("echo"):
            print(command[5:])
            continue
        print(f"{command}: command not found")


if __name__ == "__main__":
    main()