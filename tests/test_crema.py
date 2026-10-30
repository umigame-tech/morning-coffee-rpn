import io
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from crema.values import CremaError, ParseError  # noqa: E402
from crema.vm import VM  # noqa: E402


def run_cli(*args, stdin=""):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run(
        [sys.executable, "-m", "crema", *args],
        input=stdin, capture_output=True, text=True, cwd=ROOT, env=env, timeout=120,
    )


def run(src, argv=()):
    out = io.StringIO()
    vm = VM(argv=argv, stdout=out)
    vm.run_source(src, "<test>")
    return out.getvalue(), vm.stack


class LanguageTests(unittest.TestCase):
    """The language's own test suite, written in Crema (tests/lang/*.crema)."""

    def test_lang_files(self):
        lang_dir = os.path.join(ROOT, "tests", "lang")
        with tempfile.TemporaryDirectory() as tmp:
            for name in sorted(os.listdir(lang_dir)):
                with self.subTest(name):
                    r = run_cli(os.path.join("tests", "lang", name), tmp)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue(r.stdout.strip().endswith("ok"), r.stdout)


class ExampleTests(unittest.TestCase):
    def check(self, name, stdin=""):
        r = run_cli(os.path.join("examples", name + ".crema"), stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(ROOT, "tests", "expected", name + ".out"), encoding="utf-8") as f:
            self.assertEqual(r.stdout, f.read())

    def test_hello(self):
        self.check("hello")

    def test_fib(self):
        self.check("fib")

    def test_fizzbuzz(self):
        self.check("fizzbuzz")

    def test_quicksort(self):
        self.check("quicksort")

    def test_errors(self):
        self.check("errors")

    def test_brainfuck(self):
        self.check("brainfuck")

    def test_calc(self):
        self.check("calc", stdin="3 4 + 2 *\n1 0 /\nq\n")

    def test_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, "-m", "crema", os.path.join(ROOT, "examples", "files.crema")],
                capture_output=True, text=True, cwd=tmp, env=dict(os.environ, PYTHONPATH=ROOT),
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("total: 15", r.stdout)
            self.assertEqual(os.listdir(tmp), [])

    def test_wc(self):
        r = run_cli("examples/wc.crema", "examples/hello.crema")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"^\s+\d+\s+\d+\s+\d+ examples/hello.crema\n$")

    def test_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, PYTHONPATH=ROOT, TODO_FILE=os.path.join(tmp, "todo.txt"))

            def todo(*args):
                return subprocess.run(
                    [sys.executable, "-m", "crema", "examples/todo.crema", *args],
                    capture_output=True, text=True, cwd=ROOT, env=env,
                ).stdout

            todo("add", "grind", "beans")
            todo("add", "brew")
            todo("done", "1")
            self.assertEqual(todo("list"), " 1. [x] grind beans\n 2. [ ] brew\n")


class CliTests(unittest.TestCase):
    def test_eval_and_args(self):
        r = run_cli("-e", "args \" \" join println", "a", "b")
        self.assertEqual(r.stdout, "a b\n")

    def test_program_args(self):
        with tempfile.NamedTemporaryFile("w", suffix=".crema", delete=False) as f:
            f.write("args len println args first println\n")
        try:
            r = run_cli(f.name, "x", "--flag")
            self.assertEqual(r.stdout, "2\nx\n")
        finally:
            os.unlink(f.name)

    def test_stdin_program(self):
        r = run_cli("-", stdin="\"from stdin\" println")
        self.assertEqual(r.stdout, "from stdin\n")

    def test_exit_code(self):
        self.assertEqual(run_cli("-e", "\"bye\" println 3 exit 4").returncode, 3)

    def test_error_reports_position_and_trace(self):
        r = run_cli("-e", ": inner \"x\" 1 + ;\n: outer inner 0 ;\nouter")
        self.assertEqual(r.returncode, 1)
        self.assertIn("<-e>:1:15: cannot apply '+' to str and int", r.stderr)
        self.assertIn("in inner\n  in outer", r.stderr)

    def test_missing_file(self):
        r = run_cli("no/such/file.crema")
        self.assertEqual(r.returncode, 2)

    def test_repl(self):
        r = run_cli(stdin=": sq dup * ;\n4 sq\n{ 1\n2 }\n")
        self.assertIn("16 {1 2}", r.stdout)

    def test_shebang(self):
        with tempfile.NamedTemporaryFile("w", suffix=".crema", delete=False) as f:
            f.write("#!/usr/bin/env crema\n\"ok\" println\n")
        try:
            self.assertEqual(run_cli(f.name).stdout, "ok\n")
        finally:
            os.unlink(f.name)


class VmTests(unittest.TestCase):
    def test_stack_result(self):
        _, stack = run("1 2 + 3 *")
        self.assertEqual(stack, [9])

    def test_print_formats(self):
        out, _ = run('{1 "a" nil true 2.5} . #{"k" {1}} . [dup *] . "raw" .')
        self.assertEqual(out, '{1 "a" nil true 2.5}\n#{"k" {1}}\n[dup *]\nraw\n')

    def test_incomplete_parse(self):
        for src in ("[ 1", ": f 1", '"abc', "{ 1", "( comment"):
            with self.assertRaises(ParseError) as cm:
                run(src)
            self.assertTrue(cm.exception.incomplete, src)

    def test_parse_errors(self):
        for src in ("]", ";", "[ : f ; ]", "-> 1"):
            with self.assertRaises(ParseError) as cm:
                run(src)
            self.assertFalse(cm.exception.incomplete, src)

    def test_uncaught_error(self):
        with self.assertRaises(CremaError) as cm:
            run("1\n  drop drop")
        self.assertEqual(cm.exception.pos, ("<test>", 2, 8))

    def test_stack_overflow_is_catchable(self):
        _, stack = run(": f 1 f + ; [ f ] [ \"overflow\" contains? ] try")
        self.assertEqual(stack, [True])

    def test_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "lib.crema"), "w") as f:
                f.write(": twice 2 * ;\n")
            with open(os.path.join(tmp, "main.crema"), "w") as f:
                f.write('"lib.crema" include 21 twice println\n')
            r = run_cli(os.path.join(tmp, "main.crema"))
            self.assertEqual(r.stdout, "42\n", r.stderr)

    def test_read_line(self):
        out = io.StringIO()
        vm = VM(stdout=out, stdin=io.StringIO("alice\n"))
        vm.run_source('read-line "hi, " swap + println read-line nil = .')
        self.assertEqual(out.getvalue(), "hi, alice\ntrue\n")


if __name__ == "__main__":
    unittest.main()
