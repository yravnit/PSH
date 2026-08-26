import unittest

from app.parser import (
    parse_command,
    split_command_chains,
    extract_redirection,
    split_pipeline,
    expand_variables,
)


class TestParser(unittest.TestCase):
    def test_single_quotes_preserves_spaces(self):
        parts = parse_command("echo 'hello   world'")
        self.assertEqual(parts, ["echo", "hello   world"])

    def test_single_quotes_exact_content(self):
        parts = parse_command("echo 'hello world'")
        self.assertEqual(parts, ["echo", "hello world"])

    def test_single_quotes_concatenation(self):
        parts = parse_command("echo 'shell''test'")
        self.assertEqual(parts, ["echo", "shelltest"])

    def test_double_quotes_preserves_spaces(self):
        parts = parse_command('echo "hello   world"')
        self.assertEqual(parts, ["echo", "hello   world"])

    def test_double_quotes_exact_content(self):
        parts = parse_command('echo "hello world"')
        self.assertEqual(parts, ["echo", "hello world"])

    def test_double_quotes_escaped_double_quote(self):
        parts = parse_command(r'echo "hello \"world\""')
        self.assertEqual(parts, ["echo", 'hello "world"'])

    def test_double_quotes_escaped_backslash(self):
        parts = parse_command(r'echo "hello\\world"')
        self.assertEqual(parts, ["echo", "hello\\world"])

    def test_backslash_outside_quotes(self):
        parts = parse_command(r"echo hello\ \ \ world")
        self.assertEqual(parts, ["echo", "hello   world"])

    def test_mixed_quotes_and_escapes(self):
        parts = parse_command(r"echo 'single'\"double\"\ test")
        self.assertEqual(parts, ["echo", 'single"double" test'])

    def test_pipe_inside_double_quotes_not_split(self):
        parts = parse_command('echo "hello | world"')
        self.assertEqual(parts, ["echo", "hello | world"])

    def test_pipe_inside_single_quotes_not_split(self):
        parts = parse_command("echo 'hello | world'")
        self.assertEqual(parts, ["echo", "hello | world"])

    def test_and_operator_inside_quotes_not_split(self):
        parts = parse_command('echo "hello && world"')
        self.assertEqual(parts, ["echo", "hello && world"])

    def test_semicolon_inside_quotes_not_split(self):
        parts = parse_command("echo 'hello; world'")
        self.assertEqual(parts, ["echo", "hello; world"])

    def test_redirection_inside_quotes_not_split(self):
        parts = parse_command('echo "hello > output.txt"')
        self.assertEqual(parts, ["echo", "hello > output.txt"])

    def test_control_operators_tokenization_with_spaces(self):
        parts = parse_command("mkdir test && cd test")
        self.assertEqual(parts, ["mkdir", "test", "&&", "cd", "test"])

        parts = parse_command("echo hello || echo failed")
        self.assertEqual(parts, ["echo", "hello", "||", "echo", "failed"])

        parts = parse_command("echo one; echo two")
        self.assertEqual(parts, ["echo", "one", ";", "echo", "two"])

    def test_control_operators_tokenization_without_spaces(self):
        parts = parse_command("mkdir test&&cd test")
        self.assertEqual(parts, ["mkdir", "test", "&&", "cd", "test"])

        parts = parse_command("echo hello||echo failed")
        self.assertEqual(parts, ["echo", "hello", "||", "echo", "failed"])

        parts = parse_command("echo one;echo two")
        self.assertEqual(parts, ["echo", "one", ";", "echo", "two"])

    def test_split_command_chains_single(self):
        parts = ["echo", "hello"]
        chains = split_command_chains(parts)
        self.assertEqual(chains, [(None, ["echo", "hello"])])

    def test_split_command_chains_and_or_semicolon(self):
        parts = ["mkdir", "test", "&&", "cd", "test"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["mkdir", "test"]), ("&&", ["cd", "test"])]
        )

        parts = ["false", "||", "echo", "fallback"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["false"]), ("||", ["echo", "fallback"])]
        )

        parts = ["echo", "one", ";", "echo", "two"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["echo", "one"]), (";", ["echo", "two"])]
        )

    def test_split_command_chains_compound(self):
        parts = ["false", "&&", "echo", "no", "||", "echo", "yes"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["false"]), ("&&", ["echo", "no"]), ("||", ["echo", "yes"])]
        )

    def test_split_command_chains_trailing_semicolon(self):
        parts = ["echo", "one", ";", "echo", "two", ";"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["echo", "one"]), (";", ["echo", "two"]), (";", [])]
        )

    def test_split_command_chains_ampersand(self):
        parts = ["sleep", "5", "&", "jobs"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["sleep", "5", "&"]), (None, ["jobs"])]
        )

        parts = ["sleep", "5", "&"]
        self.assertEqual(
            split_command_chains(parts),
            [(None, ["sleep", "5", "&"])]
        )

    def test_expand_variables_dollar_syntax(self):
        expanded = expand_variables(["echo", "$NAME"], {"NAME": "Ronit"}, 0)
        self.assertEqual(expanded, ["echo", "Ronit"])

    def test_expand_variables_braced_syntax(self):
        expanded = expand_variables(["echo", "${NAME}"], {"NAME": "Ronit"}, 0)
        self.assertEqual(expanded, ["echo", "Ronit"])

    def test_expand_variables_exit_status(self):
        expanded = expand_variables(["echo", "$?"], {}, 42)
        self.assertEqual(expanded, ["echo", "42"])

    def test_expand_variables_unset_pruned(self):
        expanded = expand_variables(["echo", "$UNSET_VAR"], {}, 0)
        self.assertEqual(expanded, ["echo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
