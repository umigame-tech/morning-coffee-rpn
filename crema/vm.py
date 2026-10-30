"""The Crema virtual machine.

Execution never recurses on the Python stack: every running piece of code is a
Frame on `vm.tasks`, and control words (if, while, each, try, ...) push small
task objects that drive their quotes step by step. That gives deep recursion,
proper tail calls and catchable errors without Python recursion limits.
"""

import os
import sys

from .parser import parse
from .values import (
    Bind,
    Collect,
    CremaError,
    Env,
    Function,
    Quote,
    QuoteLit,
    Word,
    truthy,
)

MAX_TASKS = 1_000_000


class Exit(Exception):
    """Raised by `exit`; never caught by `try`."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class BreakSignal(Exception):
    pass


class Frame:
    __slots__ = ("code", "ip", "env", "name")

    def __init__(self, code, env, name=None):
        self.code = code
        self.ip = 0
        self.env = env
        self.name = name


# ------------------------------------------------------------------- tasks
# A task sits on vm.tasks and is resumed whenever everything above it is done.

class Task:
    __slots__ = ()
    is_loop = False


class WhileTask(Task):
    __slots__ = ("cond", "body", "checking")
    is_loop = True

    def __init__(self, cond, body):
        self.cond, self.body, self.checking = cond, body, False

    def resume(self, vm):
        if self.checking:
            self.checking = False
            if truthy(vm.pop()):
                vm.push_quote(self.body)
            else:
                vm.tasks.pop()
        else:
            self.checking = True
            vm.push_quote(self.cond)


class TimesTask(Task):
    __slots__ = ("left", "body")
    is_loop = True

    def __init__(self, n, body):
        self.left, self.body = n, body

    def resume(self, vm):
        if self.left > 0:
            self.left -= 1
            vm.push_quote(self.body)
        else:
            vm.tasks.pop()


class ForTask(Task):
    __slots__ = ("i", "end", "step", "body")
    is_loop = True

    def __init__(self, start, end, step, body):
        self.i, self.end, self.step, self.body = start, end, step, body

    def resume(self, vm):
        i = self.i
        if (self.step > 0 and i < self.end) or (self.step < 0 and i > self.end):
            self.i = i + self.step
            vm.stack.append(i)
            vm.push_quote(self.body)
        else:
            vm.tasks.pop()


class EachTask(Task):
    __slots__ = ("items", "idx", "body")
    is_loop = True

    def __init__(self, items, body):
        self.items, self.idx, self.body = items, 0, body

    def resume(self, vm):
        if self.idx < len(self.items):
            vm.stack.append(self.items[self.idx])
            self.idx += 1
            vm.push_quote(self.body)
        else:
            vm.tasks.pop()


class LoopTask(Task):
    __slots__ = ("body",)
    is_loop = True

    def __init__(self, body):
        self.body = body

    def resume(self, vm):
        vm.push_quote(self.body)


class TryTask(Task):
    __slots__ = ("handler", "depth")

    def __init__(self, handler, depth):
        self.handler, self.depth = handler, depth

    def resume(self, vm):
        vm.tasks.pop()  # the body finished without an error


class CollectTask(Task):
    __slots__ = ("depth", "is_dict", "pos")

    def __init__(self, depth, is_dict, pos):
        self.depth, self.is_dict, self.pos = depth, is_dict, pos

    def resume(self, vm):
        vm.tasks.pop()
        stack = vm.stack
        if len(stack) < self.depth:
            raise CremaError("values below '{' were consumed inside it", self.pos)
        items = stack[self.depth:]
        del stack[self.depth:]
        if not self.is_dict:
            stack.append(items)
            return
        if len(items) % 2:
            raise CremaError("'#{' needs an even number of values (key value pairs)", self.pos)
        d = {}
        for k in range(0, len(items), 2):
            d[hashable(items[k], self.pos)] = items[k + 1]
        stack.append(d)


def hashable(key, pos=None):
    if type(key) in (list, dict, Quote):
        raise CremaError("lists, dicts and quotes cannot be dict keys", pos)
    return key


# ---------------------------------------------------------------------- VM

class VM:
    def __init__(self, argv=(), stdout=None, stdin=None, prelude=True):
        from .builtins import BUILTINS

        self.stack = []
        self.tasks = []
        self.globals = Env()
        self.functions = {}
        self.builtins = BUILTINS
        self.argv = list(argv)
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stdin = stdin if stdin is not None else sys.stdin
        self.cur = None  # the word being executed, for error positions
        if prelude:
            path = os.path.join(os.path.dirname(__file__), "prelude.crema")
            with open(path, encoding="utf-8") as f:
                self.run_source(f.read(), "<prelude>")

    # -- stack helpers used by builtins
    def pop(self):
        try:
            return self.stack.pop()
        except IndexError:
            raise CremaError("stack underflow") from None

    def push(self, v):
        self.stack.append(v)

    def push_quote(self, q):
        if type(q) is not Quote:
            raise CremaError(f"expected a quote, got {_tname(q)}")
        if len(self.tasks) >= MAX_TASKS:
            raise CremaError("call stack overflow (recursion too deep)")
        self.tasks.append(Frame(q.items, q.env))

    def define(self, name, body, env, pos=None):
        self.functions[name] = Function(name, body, env, pos)

    # -- entry points
    def load(self, src, filename):
        """Parse source, register its definitions and schedule its code."""
        defs, code = parse(src, filename)
        for d in defs:
            self.define(d.name, d.body, self.globals, d.pos)
        if len(self.tasks) >= MAX_TASKS:
            raise CremaError("call stack overflow (recursion too deep)")
        self.tasks.append(Frame(code, self.globals, None))

    def run_source(self, src, filename="<input>"):
        base = len(self.tasks)
        self.load(src, filename)
        self.run(base)

    def run_file(self, path):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if src.startswith("#!"):
            src = "#" + src[1:]  # keep line numbers; '#' starts a comment anyway
        self.run_source(src, path)

    # -- the interpreter loop
    def run(self, base=0):
        tasks = self.tasks
        while len(tasks) > base:
            try:
                self._step_all(base)
            except CremaError as e:
                self._recover(e, base)
            except BreakSignal:
                self._break(base)
            except (Exit, KeyboardInterrupt):
                del self.tasks[base:]
                raise
            except RecursionError:
                self._recover(CremaError("nesting too deep"), base)
            except (ZeroDivisionError, OverflowError, ValueError, TypeError, OSError, UnicodeError) as e:
                self._recover(CremaError(_python_error_message(e)), base)

    def _step_all(self, base):
        tasks = self.tasks
        stack = self.stack
        functions = self.functions
        builtins = self.builtins
        while len(tasks) > base:
            t = tasks[-1]
            if t.__class__ is not Frame:
                t.resume(self)
                continue
            code = t.code
            ip = t.ip
            if ip >= len(code):
                tasks.pop()
                continue
            tok = code[ip]
            env = t.env
            ip += 1
            t.ip = ip
            tail = ip == len(code)
            cls = tok.__class__
            if cls is Word:
                name = tok.name
                e = env
                while e is not None:
                    vars_ = e.vars
                    if name in vars_:
                        stack.append(vars_[name])
                        break
                    e = e.parent
                else:
                    self.cur = tok
                    fn = functions.get(name)
                    if fn is not None:
                        if tail:
                            tasks.pop()  # tail call: replace the finished frame
                        elif len(tasks) >= MAX_TASKS:
                            raise CremaError("call stack overflow (recursion too deep)")
                        tasks.append(Frame(fn.body, Env(fn.env), name))
                    else:
                        b = builtins.get(name)
                        if b is None:
                            raise CremaError(f"unknown word '{name}'")
                        if tail:
                            # Keep the frame while the builtin runs so errors show it in
                            # the trace; if it scheduled new work (if, call, while...),
                            # drop the finished frame from underneath for tail calls.
                            idx = len(tasks) - 1
                            b(self)
                            if len(tasks) > idx + 1 and tasks[idx] is t:
                                del tasks[idx]
                        else:
                            b(self)
            elif cls is QuoteLit:
                stack.append(Quote(tok.items, env))
            elif cls is Bind:
                if not stack:
                    self.cur = tok
                    raise CremaError(f"stack underflow in '-> {tok.name}'")
                env.vars[tok.name] = stack.pop()
            elif cls is Collect:
                tasks.append(CollectTask(len(stack), tok.is_dict, tok.pos))
                tasks.append(Frame(tok.items, env))
            else:
                stack.append(tok)

    def _trace(self, base):
        names = [t.name for t in self.tasks[base:] if t.__class__ is Frame and t.name]
        return names[::-1]

    def _recover(self, err, base):
        if err.pos is None and self.cur is not None:
            err.pos = self.cur.pos
        if not err.trace:
            err.trace = self._trace(base)
        tasks = self.tasks
        for i in range(len(tasks) - 1, base - 1, -1):
            t = tasks[i]
            if t.__class__ is TryTask:
                del tasks[i:]
                del self.stack[t.depth:]
                self.stack.append(err.message)
                self.push_quote(t.handler)
                return
        del tasks[base:]
        raise err

    def _break(self, base):
        tasks = self.tasks
        for i in range(len(tasks) - 1, base - 1, -1):
            if tasks[i].is_loop if tasks[i].__class__ is not Frame else False:
                del tasks[i:]
                return
        self._recover(CremaError("'break' used outside of a loop"), base)


def _tname(v):
    from .values import type_name

    return type_name(v)


def _python_error_message(e):
    if isinstance(e, ZeroDivisionError):
        return "division by zero"
    if isinstance(e, OSError):
        if e.filename is not None:
            return f"{e.strerror or 'I/O error'}: {e.filename}"
        return str(e)
    return str(e)
