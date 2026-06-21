import sys
import unittest
from io import StringIO
import app.main as shell


class TestPipelines(unittest.TestCase):
    def test_split_pipeline(self):
        parts = ["cat", "file.txt", "|", "grep", "hello", "|", "wc", "-l"]
        commands = shell.split_pipeline(parts)
        self.assertEqual(commands, [
            ["cat", "file.txt"],
            ["grep", "hello"],
            ["wc", "-l"],
        ])

    def test_run_builtin_capture(self):
        output = shell.run_builtin_capture(["echo", "hello world"])
        self.assertEqual(output.decode(), "hello world\n")

    def test_pipeline_builtin_to_external(self):
        py = sys.executable.replace("\\", "/")
        cmd = f'echo hello | "{py}" -c "import sys; print(sys.stdin.read().strip().upper())"'
        out = StringIO()
        status = shell.execute_line(cmd, stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue().strip(), "HELLO")

    def test_pipeline_multi_stage(self):
        py = sys.executable.replace("\\", "/")
        cmd = (
            f'echo hello | '
            f'"{py}" -c "import sys; sys.stdout.write(sys.stdin.read().strip().upper())" | '
            f'"{py}" -c "import sys; print(len(sys.stdin.read()))"'
        )
        out = StringIO()
        status = shell.execute_line(cmd, stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue().strip(), "5")

    def test_pipeline_exit_code_propagation(self):
        py = sys.executable.replace("\\", "/")
        cmd = f'echo test | "{py}" -c "import sys; sys.exit(3)"'
        out = StringIO()
        status = shell.execute_line(cmd, stdout_stream=out)
        self.assertEqual(status, 3)
        self.assertEqual(shell.last_exit_status, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
