import os
import tempfile
import unittest
from io import StringIO
import app.main as shell


class TestControlOperators(unittest.TestCase):
    def setUp(self):
        shell.last_exit_status = 0

    def test_and_operator_success(self):
        out = StringIO()
        status = shell.execute_line("true && echo success", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "success\n")

    def test_and_operator_short_circuit_on_failure(self):
        out = StringIO()
        status = shell.execute_line("false && echo never_runs", stdout_stream=out)
        self.assertEqual(status, 1)
        self.assertEqual(out.getvalue(), "")

    def test_or_operator_fallback_on_failure(self):
        out = StringIO()
        status = shell.execute_line("false || echo fallback", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "fallback\n")

    def test_or_operator_short_circuit_on_success(self):
        out = StringIO()
        status = shell.execute_line("true || echo never_runs", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "")

    def test_semicolon_sequential_execution(self):
        out = StringIO()
        status = shell.execute_line("echo one; echo two", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "one\ntwo\n")

    def test_semicolon_after_failure_continues(self):
        out = StringIO()
        status = shell.execute_line("false; echo recovered", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "recovered\n")

    def test_compound_and_or_chain_with_failure(self):
        out = StringIO()
        status = shell.execute_line("false && echo nope || echo fallback", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "fallback\n")

    def test_compound_and_or_chain_with_success(self):
        out = StringIO()
        status = shell.execute_line("true && echo first || echo second", stdout_stream=out)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), "first\n")

    def test_directory_creation_and_cd_chain(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.chdir(tmpdir)
                status = shell.execute_line("cd . && pwd", stdout_stream=StringIO())
                self.assertEqual(status, 0)
            finally:
                os.chdir(original_cwd)

    def test_chain_exit_status_preserved_for_variable(self):
        out = StringIO()
        shell.execute_line("false && echo nope; echo $?", stdout_stream=out)
        self.assertEqual(out.getvalue(), "1\n")

    def test_ampersand_chain_execution(self):
        out = StringIO()
        shell.execute_line("echo first & echo second", stdout_stream=out)
        self.assertIn("second\n", out.getvalue())



if __name__ == "__main__":
    unittest.main(verbosity=2)
