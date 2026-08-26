"""
Command execution: process launching, pipeline orchestration, and redirection.

find_executable_path is the canonical PATH lookup used by both the executor
and builtin_type.
"""

import io
import os
import subprocess
import sys
from io import StringIO

from app.parser import split_pipeline, expand_variables, extract_redirection
from app.builtins import is_builtin, dispatch, ShellContext


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


def _write_output(output, stdout_stream):
    stdout_stream.write(output)
    stdout_stream.flush()


def _write_error(error, stderr_stream):
    stderr_stream.write(error)
    stderr_stream.flush()


def reap_jobs(ctx, stdout_stream):
    """Poll finished background jobs and print completion notices."""
    jobs_to_remove = []

    for index, job in enumerate(ctx.jobs):
        if job["process"].poll() is None:
            continue

        if index == len(ctx.jobs) - 1:
            marker = "+"
        elif index == len(ctx.jobs) - 2:
            marker = "-"
        else:
            marker = " "

        command_text = job["command"].removesuffix(" &")

        output = (
            f"[{job['job_id']}]{marker}  "
            f"{'Done':<24}"
            f"{command_text}\n"
        )

        _write_output(output, stdout_stream)
        jobs_to_remove.append(job)

    for job in jobs_to_remove:
        ctx.jobs.remove(job)


def _run_builtin_capture(parts, ctx):
    """Run a builtin and return its stdout as bytes (used inside pipelines)."""
    buffer = StringIO()
    dispatch(parts[0], parts, ctx, buffer, sys.stderr)
    return buffer.getvalue().encode()


def run_pipeline(commands, ctx, stdout_stream=sys.stdout, stderr_stream=sys.stderr):
    """Execute a list of per-stage token lists connected by pipes."""
    processes = []
    previous_pipe = None
    last_exit_code = 0
    last_process_to_capture = None

    for index, command in enumerate(commands):
        last_command = (index == len(commands) - 1)

        if is_builtin(command[0]):
            if previous_pipe:
                previous_pipe.close()
                previous_pipe = None

            buffer = StringIO()
            ret = dispatch(command[0], command, ctx, buffer, stderr_stream)
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
                _write_error(f"{command[0]}: command not found\n", stderr_stream)
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
                _write_error(f"{command[0]}: {e}\n", stderr_stream)
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


def execute_pipeline_or_command(parts, ctx, default_stdout=sys.stdout, default_stderr=sys.stderr):
    """Execute a single command or pipeline, handling background and redirection."""
    if not parts:
        return 0

    background = False
    if parts and parts[-1] == "&":
        background = True
        parts = parts[:-1]

    if not parts:
        return 0

    # Extract redirection tokens first so they don't get passed to the command,
    # then expand variables in both the command tokens AND the redirect targets.
    parts, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
    parts = expand_variables(parts, ctx.variables, ctx.last_exit_status)

    # Expand variables in redirect filenames too.
    if stdout_file:
        stdout_file = expand_variables([stdout_file], ctx.variables, ctx.last_exit_status)
        stdout_file = stdout_file[0] if stdout_file else None
    if stderr_file:
        stderr_file = expand_variables([stderr_file], ctx.variables, ctx.last_exit_status)
        stderr_file = stderr_file[0] if stderr_file else None

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
            return run_pipeline(commands, ctx, stdout_stream, stderr_stream)

        command = parts[0]

        if is_builtin(command):
            code = dispatch(command, parts, ctx, stdout_stream, stderr_stream)
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
                job_id = ctx.next_job_id()
                ctx.jobs.append({
                    "job_id": job_id,
                    "pid": process.pid,
                    "command": " ".join(parts) + " &",
                    "process": process
                })
                _write_output(
                    f"[{job_id}] {process.pid}\n",
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
            _write_error(
                f"{command}: command not found\n",
                stderr_stream
            )
            return 127
    except Exception as e:
        _write_error(f"shell: {e}\n", stderr_stream)
        return 1
    finally:
        for stream in opened_streams:
            stream.close()


def execute_line(line, ctx, stdout_stream=sys.stdout, stderr_stream=sys.stderr):
    """Parse and execute a raw input line. Updates ctx.last_exit_status."""
    from app.parser import parse_command, split_command_chains

    parts = parse_command(line)
    if not parts:
        return ctx.last_exit_status

    chains = split_command_chains(parts)

    for op, cmd_tokens in chains:
        if not cmd_tokens:
            continue

        if op is None or op == ";":
            ctx.last_exit_status = execute_pipeline_or_command(
                cmd_tokens, ctx, stdout_stream, stderr_stream
            )
        elif op == "&&":
            if ctx.last_exit_status == 0:
                ctx.last_exit_status = execute_pipeline_or_command(
                    cmd_tokens, ctx, stdout_stream, stderr_stream
                )
        elif op == "||":
            if ctx.last_exit_status != 0:
                ctx.last_exit_status = execute_pipeline_or_command(
                    cmd_tokens, ctx, stdout_stream, stderr_stream
                )

    return ctx.last_exit_status
