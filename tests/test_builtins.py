import os
import sys
import tempfile
import unittest
from io import StringIO

import app.main as shell


class TestBuiltins(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        shell.history.clear()
        shell.history_cursor = 0
        shell.variables.clear()

    def tearDown(self):
        os.chdir(self.original_cwd)

    # --- echo ---
    def test_echo_basic(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_echo(["echo", "hello", "world"], stdout, stderr)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "hello world\n")

    def test_echo_empty(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_echo(["echo"], stdout, stderr)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), "\n")

    # --- pwd ---
    def test_pwd(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_pwd(["pwd"], stdout, stderr)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), os.getcwd())

    # --- cd ---
    def test_cd_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = StringIO()
            stderr = StringIO()
            code = shell.builtin_cd(["cd", tmpdir], stdout, stderr)
            self.assertEqual(code, 0)
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(tmpdir))
            os.chdir(self.original_cwd)

    def test_cd_relative_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)
            os.chdir(tmpdir)

            stdout = StringIO()
            stderr = StringIO()
            code = shell.builtin_cd(["cd", "sub"], stdout, stderr)
            self.assertEqual(code, 0)
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(subdir))
            os.chdir(self.original_cwd)

    def test_cd_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)
            os.chdir(subdir)

            stdout = StringIO()
            stderr = StringIO()
            code = shell.builtin_cd(["cd", ".."], stdout, stderr)
            self.assertEqual(code, 0)
            self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(tmpdir))
            os.chdir(self.original_cwd)

    def test_cd_home_tilde(self):
        with tempfile.TemporaryDirectory() as fake_home:
            old_home = os.environ.get("HOME", "")
            os.environ["HOME"] = fake_home
            try:
                stdout = StringIO()
                stderr = StringIO()
                code = shell.builtin_cd(["cd", "~"], stdout, stderr)
                self.assertEqual(code, 0)
                self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(fake_home))
                os.chdir(self.original_cwd)
            finally:
                if old_home:
                    os.environ["HOME"] = old_home

    def test_cd_non_existent_directory(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_cd(["cd", "/non_existent_path_xyz_123"], stdout, stderr)
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "cd: /non_existent_path_xyz_123: No such file or directory\n")

    # --- type ---
    def test_type_builtins(self):
        for cmd in ["echo", "exit", "type", "pwd", "cd", "true", "false", "declare", "jobs", "history"]:
            stdout = StringIO()
            stderr = StringIO()
            code = shell.builtin_type(["type", cmd], stdout, stderr)
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), f"{cmd} is a shell builtin\n")

    def test_type_not_found(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_type(["type", "non_existent_command_123"], stdout, stderr)
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "non_existent_command_123: not found\n")

    def test_type_executable_in_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bin = os.path.join(tmpdir, "my_custom_exe")
            with open(fake_bin, "w") as f:
                f.write("#!/bin/sh\necho custom\n")
            os.chmod(fake_bin, 0o755)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                stdout = StringIO()
                stderr = StringIO()
                code = shell.builtin_type(["type", "my_custom_exe"], stdout, stderr)
                self.assertEqual(code, 0)
                self.assertEqual(stdout.getvalue(), f"my_custom_exe is {fake_bin}\n")
            finally:
                os.environ["PATH"] = old_path

    # --- true and false ---
    def test_true_builtin(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_true(["true"], stdout, stderr)
        self.assertEqual(code, 0)

    def test_false_builtin(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_false(["false"], stdout, stderr)
        self.assertEqual(code, 1)

    # --- exit ---
    def test_exit_default(self):
        stdout = StringIO()
        stderr = StringIO()
        with self.assertRaises(SystemExit) as cm:
            shell.builtin_exit(["exit"], stdout, stderr)
        self.assertEqual(cm.exception.code, 0)

    def test_exit_with_code(self):
        stdout = StringIO()
        stderr = StringIO()
        with self.assertRaises(SystemExit) as cm:
            shell.builtin_exit(["exit", "42"], stdout, stderr)
        self.assertEqual(cm.exception.code, 42)

    # --- history ---
    def test_history_display(self):
        shell.history.extend(["echo one", "pwd", "exit"])
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_history(["history"], stdout, stderr)
        self.assertEqual(code, 0)
        lines = [line.strip() for line in stdout.getvalue().strip().split("\n")]
        self.assertEqual(lines, ["1  echo one", "2  pwd", "3  exit"])

    def test_history_limit(self):
        shell.history.extend(["cmd1", "cmd2", "cmd3", "cmd4"])
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_history(["history", "2"], stdout, stderr)
        self.assertEqual(code, 0)
        lines = [line.strip() for line in stdout.getvalue().strip().split("\n")]
        self.assertEqual(lines, ["3  cmd3", "4  cmd4"])

    def test_history_file_flags(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            filepath = f.name

        try:
            shell.history.extend(["echo a", "echo b"])
            code_w = shell.builtin_history(["history", "-w", filepath], StringIO(), StringIO())
            self.assertEqual(code_w, 0)

            shell.history.clear()
            code_r = shell.builtin_history(["history", "-r", filepath], StringIO(), StringIO())
            self.assertEqual(code_r, 0)
            self.assertEqual(shell.history, ["echo a", "echo b"])

            shell.history.append("echo c")
            code_a = shell.builtin_history(["history", "-a", filepath], StringIO(), StringIO())
            self.assertEqual(code_a, 0)

            with open(filepath, "r") as f:
                content = f.read().splitlines()
            self.assertEqual(content, ["echo a", "echo b", "echo c"])
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)


if __name__ == "__main__":
    unittest.main(verbosity=2)
