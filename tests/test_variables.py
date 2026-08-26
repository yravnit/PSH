import unittest
from io import StringIO

from app.builtins import ShellContext
from app.executor import execute_line


def fresh_ctx():
    return ShellContext()


class TestVariables(unittest.TestCase):
    def test_declare_assignment_and_lookup(self):
        c = fresh_ctx()
        out = StringIO()
        err = StringIO()
        status = execute_line("declare NAME=Ronit", c, out, err)
        self.assertEqual(status, 0)
        self.assertEqual(c.variables.get("NAME"), "Ronit")

    def test_declare_print_existing(self):
        c = fresh_ctx()
        c.variables["NAME"] = "Ronit"
        out = StringIO()
        err = StringIO()
        status = execute_line("declare -p NAME", c, out, err)
        self.assertEqual(status, 0)
        self.assertEqual(out.getvalue(), 'declare -- NAME="Ronit"\n')

    def test_declare_print_missing(self):
        c = fresh_ctx()
        out = StringIO()
        err = StringIO()
        status = execute_line("declare -p UNSET_VAR", c, out, err)
        self.assertEqual(status, 1)
        self.assertEqual(err.getvalue(), "declare: UNSET_VAR: not found\n")

    def test_declare_invalid_identifier(self):
        c = fresh_ctx()
        out = StringIO()
        err = StringIO()
        status = execute_line("declare 123INVALID=value", c, out, err)
        self.assertEqual(status, 1)
        self.assertIn("not a valid identifier", err.getvalue())

    def test_expand_var_dollar_syntax(self):
        c = fresh_ctx()
        c.variables["NAME"] = "Ronit"
        out = StringIO()
        execute_line("echo $NAME", c, out)
        self.assertEqual(out.getvalue(), "Ronit\n")

    def test_expand_var_braced_syntax(self):
        c = fresh_ctx()
        c.variables["NAME"] = "Ronit"
        out = StringIO()
        execute_line("echo ${NAME}", c, out)
        self.assertEqual(out.getvalue(), "Ronit\n")

    def test_expand_var_interpolation(self):
        c = fresh_ctx()
        c.variables["NAME"] = "Ronit"
        out = StringIO()
        execute_line("echo ${NAME}_developer", c, out)
        self.assertEqual(out.getvalue(), "Ronit_developer\n")

    def test_expand_unset_var_pruned(self):
        c = fresh_ctx()
        out = StringIO()
        execute_line("echo $NON_EXISTENT_VAR", c, out)
        # Pruned empty arg means echo prints just a newline
        self.assertEqual(out.getvalue(), "\n")

    def test_exit_status_variable_success(self):
        c = fresh_ctx()
        c.last_exit_status = 0
        out = StringIO()
        execute_line("echo $?", c, out)
        self.assertEqual(out.getvalue(), "0\n")

    def test_exit_status_variable_failure(self):
        c = fresh_ctx()
        c.last_exit_status = 1
        out = StringIO()
        execute_line("echo $?", c, out)
        self.assertEqual(out.getvalue(), "1\n")

    def test_exit_status_integration(self):
        c = fresh_ctx()
        execute_line("false", c, StringIO())
        self.assertEqual(c.last_exit_status, 1)

        out = StringIO()
        execute_line("echo $?", c, out)
        self.assertEqual(out.getvalue(), "1\n")
        self.assertEqual(c.last_exit_status, 0)

        out2 = StringIO()
        execute_line("echo $?", c, out2)
        self.assertEqual(out2.getvalue(), "0\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
