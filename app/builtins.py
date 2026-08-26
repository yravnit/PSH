"""
Shell builtin command handlers.

All handlers follow the signature:
    fn(args: list[str], ctx: ShellContext) -> int

ShellContext carries the mutable shell state each builtin needs. Handlers
never reach for module-level globals.
"""

import os
import sys
from dataclasses import dataclass, field


@dataclass
class ShellContext:
    """Mutable shell state passed to every builtin handler."""
    jobs: list = field(default_factory=list)
    history: list = field(default_factory=list)
    history_cursor: int = 0
    variables: dict = field(default_factory=dict)
    last_exit_status: int = 0
    _next_job_id: int = 1

    def next_job_id(self):
        jid = self._next_job_id
        self._next_job_id += 1
        return jid


def _write_output(output, stdout_stream):
    stdout_stream.write(output)
    stdout_stream.flush()


def _write_error(error, stderr_stream):
    stderr_stream.write(error)
    stderr_stream.flush()


def _is_valid_identifier(name):
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in name)


# ---------------------------------------------------------------------------
# History persistence helpers
# ---------------------------------------------------------------------------

def history_read(path, ctx):
    with open(path, "r") as f:
        for line in f:
            command = line.rstrip("\n")
            if command:
                ctx.history.append(command)
    ctx.history_cursor = len(ctx.history)


def history_write(path, ctx):
    with open(path, "w") as f:
        for command in ctx.history:
            f.write(command + "\n")
    ctx.history_cursor = len(ctx.history)


def history_append(path, ctx):
    with open(path, "a") as f:
        for command in ctx.history[ctx.history_cursor:]:
            f.write(command + "\n")
    ctx.history_cursor = len(ctx.history)


def load_history_on_startup(ctx):
    histfile = os.environ.get("HISTFILE")
    if not histfile:
        return
    try:
        history_read(histfile, ctx)
    except OSError:
        pass


def save_history_on_exit(ctx):
    histfile = os.environ.get("HISTFILE")
    if not histfile:
        return
    try:
        history_write(histfile, ctx)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Builtin handlers
# ---------------------------------------------------------------------------

def builtin_echo(args, ctx, stdout_stream, stderr_stream):
    _write_output(" ".join(args[1:]) + '\n', stdout_stream)
    return 0


def builtin_pwd(args, ctx, stdout_stream, stderr_stream):
    _write_output(os.getcwd() + "\n", stdout_stream)
    return 0


def builtin_type(args, ctx, stdout_stream, stderr_stream):
    if len(args) < 2:
        return 1

    from app.executor import find_executable_path

    exit_code = 0
    for target in args[1:]:
        if is_builtin(target):
            output = f"{target} is a shell builtin\n"
        else:
            executable_path = find_executable_path(target)
            if executable_path:
                output = f"{target} is {executable_path}\n"
            else:
                output = f"{target}: not found\n"
                exit_code = 1

        _write_output(output, stdout_stream)

    return exit_code


def builtin_cd(args, ctx, stdout_stream, stderr_stream):
    if len(args) < 2:
        path = os.path.expanduser("~")
    else:
        path = args[1]

    # Expand leading ~/ or bare ~
    if path == "~" or path.startswith("~/") or path.startswith("~\\"):
        path = os.path.expanduser(path)

    try:
        os.chdir(path)
        return 0
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        _write_error(
            f"cd: {path}: No such file or directory\n",
            stderr_stream
        )
        return 1


def builtin_jobs(args, ctx, stdout_stream, stderr_stream):
    jobs_to_remove = []

    for index, job in enumerate(ctx.jobs):
        if index == len(ctx.jobs) - 1:
            marker = "+"
        elif index == len(ctx.jobs) - 2:
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

        _write_output(output, stdout_stream)

    for job in jobs_to_remove:
        ctx.jobs.remove(job)

    return 0


def builtin_exit(args, ctx, stdout_stream, stderr_stream):
    save_history_on_exit(ctx)
    code = 0
    if len(args) > 1:
        try:
            code = int(args[1])
        except ValueError:
            code = 1
    sys.exit(code)


def builtin_history(args, ctx, stdout_stream, stderr_stream):
    if len(args) == 3:
        flag = args[1]
        path = args[2]

        try:
            if flag == "-r":
                history_read(path, ctx)
                return 0
            if flag == "-w":
                history_write(path, ctx)
                return 0
            if flag == "-a":
                history_append(path, ctx)
                return 0
        except OSError:
            return 1

    if len(args) > 1:
        try:
            limit = int(args[1])
            start_index = max(0, len(ctx.history) - limit)
            entries = ctx.history[start_index:]
        except ValueError:
            _write_error(f"history: {args[1]}: numeric argument required\n", stderr_stream)
            return 1
    else:
        start_index = 0
        entries = ctx.history

    for index, command in enumerate(entries, start=start_index + 1):
        _write_output(f"    {index}  {command}\n", stdout_stream)

    return 0


def builtin_declare(args, ctx, stdout_stream, stderr_stream):
    # declare -p NAME
    if len(args) == 3 and args[1] == "-p":
        name = args[2]

        if name in ctx.variables:
            _write_output(
                f'declare -- {name}="{ctx.variables[name]}"\n',
                stdout_stream
            )
            return 0
        else:
            _write_error(
                f"declare: {name}: not found\n",
                stderr_stream
            )
            return 1

    # declare NAME=value
    if len(args) == 2 and "=" in args[1]:
        name, value = args[1].split("=", 1)

        if not _is_valid_identifier(name):
            _write_error(
                f"declare: `{args[1]}': not a valid identifier\n",
                stderr_stream
            )
            return 1

        ctx.variables[name] = value
        return 0

    return 0


def builtin_true(args, ctx, stdout_stream, stderr_stream):
    return 0


def builtin_false(args, ctx, stdout_stream, stderr_stream):
    return 1


def builtin_wait(args, ctx, stdout_stream, stderr_stream):
    if len(args) > 1:
        # wait <pid> [pid ...] — wait for specific PIDs
        exit_code = 0
        for pid_str in args[1:]:
            try:
                target_pid = int(pid_str)
            except ValueError:
                _write_error(f"wait: {pid_str}: not a valid PID\n", stderr_stream)
                exit_code = 1
                continue

            job = next((j for j in ctx.jobs if j["pid"] == target_pid), None)
            if job is None:
                _write_error(f"wait: {target_pid}: no such job\n", stderr_stream)
                exit_code = 1
                continue

            job["process"].wait()
            _print_done(job, ctx, stdout_stream)
            ctx.jobs.remove(job)
        return exit_code
    else:
        # wait with no args — wait for all background jobs
        last_code = 0
        while ctx.jobs:
            job = ctx.jobs[0]
            job["process"].wait()
            last_code = job["process"].returncode or 0
            _print_done(job, ctx, stdout_stream)
            ctx.jobs.remove(job)
        return last_code


def _print_done(job, ctx, stdout_stream):
    index = ctx.jobs.index(job) if job in ctx.jobs else len(ctx.jobs) - 1
    total = len(ctx.jobs)
    if index == total - 1:
        marker = "+"
    elif index == total - 2:
        marker = "-"
    else:
        marker = " "
    command_text = job["command"].removesuffix(" &")
    stdout_stream.write(
        f"[{job['job_id']}]{marker}  {'Done':<24}{command_text}\n"
    )
    stdout_stream.flush()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_HANDLERS = {
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
    "wait": builtin_wait,
}


def is_builtin(command):
    return command in _HANDLERS


def get_builtin_names():
    return set(_HANDLERS.keys())


def dispatch(command, args, ctx, stdout_stream, stderr_stream):
    """Call the builtin handler for command. Returns its exit code."""
    return _HANDLERS[command](args, ctx, stdout_stream, stderr_stream)
