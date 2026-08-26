import os
import tempfile
import unittest
from io import StringIO

from app.builtins import ShellContext
from app.executor import execute_line
from app.parser import extract_redirection


def fresh_ctx():
    return ShellContext()


class TestRedirection(unittest.TestCase):
    def test_stdout_overwrite_redirect_parsing(self):
        parts = ["echo", "hello", ">", "out.txt"]
        cleaned, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
        self.assertEqual(cleaned, ["echo", "hello"])
        self.assertEqual(stdout_file, "out.txt")
        self.assertFalse(append_stdout)
        self.assertIsNone(stderr_file)

    def test_stdout_append_redirect_parsing(self):
        parts = ["echo", "hello", "1>>", "out.txt"]
        cleaned, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
        self.assertEqual(cleaned, ["echo", "hello"])
        self.assertEqual(stdout_file, "out.txt")
        self.assertTrue(append_stdout)
        self.assertIsNone(stderr_file)

    def test_stderr_overwrite_redirect_parsing(self):
        parts = ["ls", "non_existent", "2>", "err.log"]
        cleaned, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
        self.assertEqual(cleaned, ["ls", "non_existent"])
        self.assertEqual(stderr_file, "err.log")
        self.assertFalse(append_stderr)
        self.assertIsNone(stdout_file)

    def test_stderr_append_redirect_parsing(self):
        parts = ["ls", "non_existent", "2>>", "err.log"]
        cleaned, stdout_file, stderr_file, append_stdout, append_stderr = extract_redirection(parts)
        self.assertEqual(cleaned, ["ls", "non_existent"])
        self.assertEqual(stderr_file, "err.log")
        self.assertTrue(append_stderr)
        self.assertIsNone(stdout_file)

    def test_stdout_file_overwrite_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "output.txt").replace("\\", "/")
            cmd = f"echo hello > {out_file}"
            status = execute_line(cmd, fresh_ctx())
            self.assertEqual(status, 0)

            with open(out_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "hello\n")

            # Overwrite again
            execute_line(f"echo replacement > {out_file}", fresh_ctx())
            with open(out_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "replacement\n")

    def test_stdout_file_append_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "output.txt").replace("\\", "/")
            c = fresh_ctx()
            execute_line(f"echo first line > {out_file}", c)
            execute_line(f"echo second line >> {out_file}", c)

            with open(out_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "first line\nsecond line\n")

    def test_stderr_file_overwrite_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            err_file = os.path.join(tmpdir, "error.txt").replace("\\", "/")
            status = execute_line(f"non_existent_binary_xyz_123 2> {err_file}", fresh_ctx())
            self.assertEqual(status, 127)

            with open(err_file, "r") as f:
                content = f.read()
            self.assertIn("command not found", content)

    def test_stderr_file_append_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            err_file = os.path.join(tmpdir, "error.txt").replace("\\", "/")
            c = fresh_ctx()
            execute_line(f"cd /non_existent_directory_1 2> {err_file}", c)
            execute_line(f"cd /non_existent_directory_2 2>> {err_file}", c)

            with open(err_file, "r") as f:
                content = f.read()
            lines = [l for l in content.strip().split("\n") if l]
            self.assertEqual(len(lines), 2)
            self.assertIn("No such file or directory", lines[0])
            self.assertIn("No such file or directory", lines[1])

    def test_redirect_to_variable_filename(self):
        """Redirect target variables like $LOGFILE should be expanded before opening."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "var_out.txt").replace("\\", "/")
            c = fresh_ctx()
            c.variables["LOGFILE"] = out_file
            execute_line("echo from_var > $LOGFILE", c)

            with open(out_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "from_var\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
