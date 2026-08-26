import os
import tempfile
import unittest
from io import StringIO

from app.builtins import ShellContext
from app.executor import execute_line


def fresh_ctx():
    return ShellContext()


class TestControlOperators(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_and_operator_success(self):
        out = StringIO()
        status = execute_line("true && echo success", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "success\n")

    def test_and_operator_short_circuit_on_failure(self):
        out = StringIO()
        status = execute_line("false && echo never_runs", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 1)
        self.assertEqual(out.getvalue(), "")

    def test_or_operator_fallback_on_failure(self):
        out = StringIO()
        status = execute_line("false || echo fallback", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "fallback\n")

    def test_or_operator_short_circuit_on_success(self):
        out = StringIO()
        status = execute_line("true || echo never_runs", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "")

    def test_semicolon_sequential_execution(self):
        out = StringIO()
        status = execute_line("echo one; echo two", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "one\ntwo\n")

    def test_semicolon_after_failure_continues(self):
        out = StringIO()
        status = execute_line("false; echo recovered", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "recovered\n")

    def test_compound_and_or_chain_with_failure(self):
        out = StringIO()
        status = execute_line("false && echo nope || echo fallback", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "fallback\n")

    def test_compound_and_or_chain_with_success(self):
        out = StringIO()
        status = execute_line("true && echo first || echo second", fresh_ctx(), stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "first\n")

    def test_directory_creation_and_cd_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                status = execute_line("cd . && pwd", fresh_ctx(), stdout_stream=StringIO())
                self.assertEqual(status, 0)
            finally:
                os.chdir(self.original_cwd)

    def test_chain_exit_status_preserved_for_variable(self):
        out = StringIO()
        c = fresh_ctx()
        execute_line("false && echo nope; echo $?", c, stdout_stream=out)
        self.assertEqual(out.getvalue(), "1\n")

    def test_ampersand_chain_execution(self):
        out = StringIO()
        execute_line("echo first & echo second", fresh_ctx(), stdout_stream=out)
        self.assertIn("second\n", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
