import unittest
from io import StringIO
import app.main as shell


class TestVariables(unittest.TestCase):
    def setUp(self):
        shell.variables.clear()
        shell.last_exit_status = 0

    def test_declare_assignment_and_lookup(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_declare(["declare", "NAME=Ronit"], stdout, stderr)
        self.assertEqual(code, 0)
        self.assertEqual(shell.variables.get("NAME"), "Ronit")

    def test_declare_print_existing(self):
        shell.variables["NAME"] = "Ronit"
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_declare(["declare", "-p", "NAME"], stdout, stderr)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue(), 'declare -- NAME="Ronit"\n')

    def test_declare_print_missing(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_declare(["declare", "-p", "UNSET_VAR"], stdout, stderr)
        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "declare: UNSET_VAR: not found\n")

    def test_declare_invalid_identifier(self):
        stdout = StringIO()
        stderr = StringIO()
        code = shell.builtin_declare(["declare", "123INVALID=value"], stdout, stderr)
        self.assertEqual(code, 1)
        self.assertIn("not a valid identifier", stderr.getvalue())

    def test_expand_var_dollar_syntax(self):
        shell.variables["NAME"] = "Ronit"
        expanded = shell.expand_variables(["echo", "$NAME"])
        self.assertEqual(expanded, ["echo", "Ronit"])

    def test_expand_var_braced_syntax(self):
        shell.variables["NAME"] = "Ronit"
        expanded = shell.expand_variables(["echo", "${NAME}"])
        self.assertEqual(expanded, ["echo", "Ronit"])

    def test_expand_var_interpolation(self):
        shell.variables["NAME"] = "Ronit"
        expanded = shell.expand_variables(["echo", "${NAME}_developer", "prefix_$NAME"])
        self.assertEqual(expanded, ["echo", "Ronit_developer", "prefix_Ronit"])

    def test_expand_unset_var_pruned(self):
        expanded = shell.expand_variables(["echo", "$NON_EXISTENT_VAR"])
        self.assertEqual(expanded, ["echo"])

    def test_exit_status_variable_success(self):
        shell.last_exit_status = 0
        expanded = shell.expand_variables(["echo", "$?"])
        self.assertEqual(expanded, ["echo", "0"])

        expanded_braced = shell.expand_variables(["echo", "${?}"])
        self.assertEqual(expanded_braced, ["echo", "0"])

    def test_exit_status_variable_failure(self):
        shell.last_exit_status = 1
        expanded = shell.expand_variables(["echo", "$?"])
        self.assertEqual(expanded, ["echo", "1"])

    def test_exit_status_integration(self):
        out = StringIO()
        shell.execute_line("false", stdout_stream=out)
        self.assertEqual(shell.last_exit_status, 1)

        out = StringIO()
        shell.execute_line("echo $?", stdout_stream=out)
        self.assertEqual(out.getvalue(), "1\n")
        self.assertEqual(shell.last_exit_status, 0)

        out = StringIO()
        shell.execute_line("echo $?", stdout_stream=out)
        self.assertEqual(out.getvalue(), "0\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
