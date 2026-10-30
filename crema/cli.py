"""Command line interface: run Crema programs or start a REPL."""

import argparse
import sys

from . import __version__
from .values import CremaError, ParseError, repr_value
from .vm import VM, Exit

USAGE_EPILOG = """examples:
  crema examples/hello.crema           run a program
  crema wc.crema notes.txt             arguments are available via `args`
  crema -e '1 2 + println'             evaluate code from the command line
  crema                                start the interactive REPL
"""


def report(err):
    sys.stdout.flush()
    sys.stderr.write(f"error: {err.located()}\n")
    for name in err.trace[:20]:
        sys.stderr.write(f"  in {name}\n")
    if len(err.trace) > 20:
        sys.stderr.write(f"  ... ({len(err.trace) - 20} more)\n")


def repl(vm):
    try:
        import readline  # noqa: F401  (line editing and history)
    except ImportError:
        pass
    print(f"Crema {__version__} -- reverse Polish notation. Ctrl-D to quit.")
    buf = ""
    while True:
        try:
            line = input("... " if buf else "> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            buf = ""
            continue
        buf += line + "\n"
        try:
            vm.run_source(buf, "<repl>")
        except ParseError as e:
            if e.incomplete:
                continue
            report(e)
        except CremaError as e:
            report(e)
        except KeyboardInterrupt:
            print("\ninterrupted")
        except Exit as e:
            return e.code
        buf = ""
        sys.stdout.flush()
        if vm.stack:
            print("  " + " ".join(repr_value(v) for v in vm.stack))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="crema",
        description="Crema: a stack-based programming language in reverse Polish notation.",
        epilog=USAGE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-e", "--eval", metavar="CODE", help="run CODE instead of a file")
    parser.add_argument("-i", "--interactive", action="store_true", help="start the REPL after running")
    parser.add_argument("--version", action="version", version=f"crema {__version__}")
    parser.add_argument("file", nargs="?", help="program to run (use - for stdin)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the program")
    opts = parser.parse_args(argv)

    prog_args = ([opts.file] if opts.eval is not None and opts.file else []) + opts.args
    vm = VM(argv=prog_args if opts.eval is not None else opts.args)
    try:
        if opts.eval is not None:
            vm.run_source(opts.eval, "<-e>")
        elif opts.file == "-":
            vm.run_source(sys.stdin.read(), "<stdin>")
        elif opts.file:
            vm.run_file(opts.file)
        else:
            return repl(vm)
    except CremaError as e:
        report(e)
        return 1
    except Exit as e:
        sys.stdout.flush()
        return e.code
    except OSError as e:
        sys.stderr.write(f"crema: cannot open {opts.file}: {e.strerror}\n")
        return 2
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return 130
    finally:
        sys.stdout.flush()
    if opts.interactive:
        return repl(vm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
