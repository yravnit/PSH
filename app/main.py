import sys


def main():
    # TODO: Uncomment the code below to pass the first stage
    sys.stdout.write("$ ")
    sys.stdout.flush()

    command = sys.stdin.readline().rstrip("\n")
    print(f"{command}: command not found")


if __name__ == "__main__":
    main()