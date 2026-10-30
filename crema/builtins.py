"""Built-in words implemented in Python."""

import math
import os
import random
import sys
import time

from .values import (
    CremaError,
    Quote,
    equal,
    quote_items_as_data,
    repr_value,
    show,
    truthy,
    type_name,
)
from .vm import (
    BreakSignal,
    EachTask,
    Exit,
    ForTask,
    LoopTask,
    TimesTask,
    TryTask,
    WhileTask,
    hashable,
)

BUILTINS = {}


def word(*names):
    def register(fn):
        for name in names:
            BUILTINS[name] = fn
        return fn

    return register


# ------------------------------------------------------------ type helpers

def _fail(expected, v):
    raise CremaError(f"expected {expected}, got {type_name(v)} {repr_value(v)}")


def num(v):
    t = type(v)
    if t is int or t is float:
        return v
    _fail("a number", v)


def integer(v):
    if type(v) is int:
        return v
    if type(v) is float and v.is_integer():
        return int(v)
    _fail("an integer", v)


def string(v):
    if type(v) is str:
        return v
    _fail("a string", v)


def lst(v):
    t = type(v)
    if t is list:
        return v
    if t is Quote:
        return quote_items_as_data(v)
    _fail("a list", v)


def dct(v):
    if type(v) is dict:
        return v
    _fail("a dict", v)


def quote(v):
    if type(v) is Quote:
        return v
    _fail("a quote", v)


def sequence(v):
    """A list, quote or string (things with an order and a length)."""
    if type(v) is str:
        return v
    return lst(v)


def _index(seq, i):
    i = integer(i)
    n = len(seq)
    j = i + n if i < 0 else i
    if not 0 <= j < n:
        raise CremaError(f"index {i} out of range (length {n})")
    return j


# ------------------------------------------------------------------- stack

@word("dup")
def _dup(vm):
    s = vm.stack
    if not s:
        raise CremaError("stack underflow")
    s.append(s[-1])


@word("drop")
def _drop(vm):
    vm.pop()


@word("swap")
def _swap(vm):
    b, a = vm.pop(), vm.pop()
    vm.stack += [b, a]


@word("over")
def _over(vm):
    b, a = vm.pop(), vm.pop()
    vm.stack += [a, b, a]


@word("rot")
def _rot(vm):  # a b c -- b c a
    c, b, a = vm.pop(), vm.pop(), vm.pop()
    vm.stack += [b, c, a]


@word("-rot")
def _mrot(vm):  # a b c -- c a b
    c, b, a = vm.pop(), vm.pop(), vm.pop()
    vm.stack += [c, a, b]


@word("nip")
def _nip(vm):
    b = vm.pop()
    vm.pop()
    vm.push(b)


@word("tuck")
def _tuck(vm):  # a b -- b a b
    b, a = vm.pop(), vm.pop()
    vm.stack += [b, a, b]


@word("pick")
def _pick(vm):  # ... n -- ... x   (0 pick = dup)
    n = integer(vm.pop())
    if not 0 <= n < len(vm.stack):
        raise CremaError("stack underflow")
    vm.push(vm.stack[-1 - n])


@word("2dup")
def _2dup(vm):
    if len(vm.stack) < 2:
        raise CremaError("stack underflow")
    vm.stack += vm.stack[-2:]


@word("2drop")
def _2drop(vm):
    vm.pop()
    vm.pop()


@word("depth")
def _depth(vm):
    vm.push(len(vm.stack))


@word("clear")
def _clear(vm):
    vm.stack.clear()


@word(".s")
def _dots(vm):
    vm.stdout.write(f"<{len(vm.stack)}> " + " ".join(repr_value(v) for v in vm.stack) + "\n")


# -------------------------------------------------------------- arithmetic

def _type_pair_error(op, a, b):
    raise CremaError(f"cannot apply '{op}' to {type_name(a)} and {type_name(b)}")


@word("+")
def _add(vm):
    b, a = vm.pop(), vm.pop()
    ta, tb = type(a), type(b)
    if ta in (int, float) and tb in (int, float):
        vm.push(a + b)
    elif ta is str and tb is str:
        vm.push(a + b)
    elif ta in (list, Quote) and tb in (list, Quote):
        vm.push(lst(a) + lst(b))
    else:
        _type_pair_error("+", a, b)


@word("-")
def _sub(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(num(a) - num(b))


@word("*")
def _mul(vm):
    b, a = vm.pop(), vm.pop()
    ta, tb = type(a), type(b)
    if ta in (int, float) and tb in (int, float):
        vm.push(a * b)
    elif ta in (str, list) and tb is int:
        vm.push(a * b)
    else:
        _type_pair_error("*", a, b)


@word("/")
def _div(vm):
    b, a = num(vm.pop()), num(vm.pop())
    if b == 0:
        raise CremaError("division by zero")
    if type(a) is int and type(b) is int and a % b == 0:
        vm.push(a // b)
    else:
        vm.push(a / b)


@word("div")
def _idiv(vm):
    b, a = num(vm.pop()), num(vm.pop())
    if b == 0:
        raise CremaError("division by zero")
    r = a // b
    vm.push(int(r) if type(r) is float else r)


@word("mod", "%")
def _mod(vm):
    b, a = num(vm.pop()), num(vm.pop())
    if b == 0:
        raise CremaError("division by zero")
    vm.push(a % b)


@word("**", "pow")
def _pow(vm):
    b, a = num(vm.pop()), num(vm.pop())
    vm.push(a ** b)


def _unary(name, fn, conv=num):
    def impl(vm):
        vm.push(fn(conv(vm.pop())))

    BUILTINS[name] = impl


_unary("neg", lambda x: -x)
_unary("abs", abs)
_unary("inc", lambda x: x + 1)
_unary("dec", lambda x: x - 1)
_unary("floor", math.floor)
_unary("ceil", math.ceil)
_unary("sqrt", math.sqrt)
_unary("sin", math.sin)
_unary("cos", math.cos)
_unary("tan", math.tan)
_unary("exp", math.exp)
_unary("log", math.log)
_unary("even?", lambda x: x % 2 == 0, integer)
_unary("odd?", lambda x: x % 2 == 1, integer)
_unary("zero?", lambda x: x == 0)


@word("round")
def _round(vm):
    x = num(vm.pop())
    vm.push(int(math.floor(x + 0.5)))


@word("min")
def _min(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(b if _less(b, a) else a)


@word("max")
def _max(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(b if _less(a, b) else a)


@word("pi")
def _pi(vm):
    vm.push(math.pi)


@word("random")
def _random(vm):
    vm.push(random.random())


@word("randint")
def _randint(vm):  # lo hi -- n   (inclusive)
    hi, lo = integer(vm.pop()), integer(vm.pop())
    vm.push(random.randint(lo, hi))


# ------------------------------------------------------ comparison & logic

def _less(a, b):
    ta, tb = type(a), type(b)
    if ta in (int, float) and tb in (int, float) or (ta is str and tb is str):
        return a < b
    if ta is list and tb is list:
        for x, y in zip(a, b):
            if _less(x, y):
                return True
            if _less(y, x):
                return False
        return len(a) < len(b)
    raise CremaError(f"cannot compare {type_name(a)} and {type_name(b)}")


@word("=")
def _eq(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(equal(a, b))


@word("!=")
def _ne(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not equal(a, b))


@word("<")
def _lt(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(_less(a, b))


@word(">")
def _gt(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(_less(b, a))


@word("<=")
def _le(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not _less(b, a))


@word(">=")
def _ge(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(not _less(a, b))


@word("and")
def _and(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(truthy(a) and truthy(b))


@word("or")
def _or(vm):
    b, a = vm.pop(), vm.pop()
    vm.push(truthy(a) or truthy(b))


@word("not")
def _not(vm):
    vm.push(not truthy(vm.pop()))


@word("?")
def _choose(vm):  # cond a b -- a|b
    b, a, c = vm.pop(), vm.pop(), vm.pop()
    vm.push(a if truthy(c) else b)


# ----------------------------------------------------------------- control

@word("call")
def _call(vm):
    vm.push_quote(quote(vm.pop()))


@word("if")
def _if(vm):  # cond [then] [else] if
    else_, then, cond = quote(vm.pop()), quote(vm.pop()), vm.pop()
    vm.push_quote(then if truthy(cond) else else_)


@word("when")
def _when(vm):  # cond [then] when
    then, cond = quote(vm.pop()), vm.pop()
    if truthy(cond):
        vm.push_quote(then)


@word("unless")
def _unless(vm):  # cond [else] unless
    body, cond = quote(vm.pop()), vm.pop()
    if not truthy(cond):
        vm.push_quote(body)


@word("while")
def _while(vm):  # [cond] [body] while
    body, cond = quote(vm.pop()), quote(vm.pop())
    vm.tasks.append(WhileTask(cond, body))


@word("times")
def _times(vm):  # n [body] times
    body, n = quote(vm.pop()), integer(vm.pop())
    vm.tasks.append(TimesTask(n, body))


@word("for")
def _for(vm):  # start end [body] for    (end is exclusive; pushes the counter)
    body, end, start = quote(vm.pop()), num(vm.pop()), num(vm.pop())
    vm.tasks.append(ForTask(start, end, 1, body))


@word("for-step")
def _for_step(vm):  # start end step [body] for-step
    body, step, end, start = quote(vm.pop()), num(vm.pop()), num(vm.pop()), num(vm.pop())
    if step == 0:
        raise CremaError("for-step: step must not be 0")
    vm.tasks.append(ForTask(start, end, step, body))


@word("each")
def _each(vm):  # list [body] each
    body, coll = quote(vm.pop()), vm.pop()
    if type(coll) is dict:
        items = [[k, v] for k, v in coll.items()]
    else:
        items = list(sequence(coll))
    vm.tasks.append(EachTask(items, body))


@word("loop")
def _loop(vm):  # [body] loop   (until break)
    vm.tasks.append(LoopTask(quote(vm.pop())))


@word("break")
def _break(vm):
    raise BreakSignal()


@word("try")
def _try(vm):  # [body] [handler] try   (handler receives the error message)
    handler, body = quote(vm.pop()), quote(vm.pop())
    vm.tasks.append(TryTask(handler, len(vm.stack)))
    vm.push_quote(body)


@word("throw")
def _throw(vm):
    raise CremaError(show(vm.pop()))


@word("assert")
def _assert(vm):  # cond message assert
    msg, cond = vm.pop(), vm.pop()
    if not truthy(cond):
        raise CremaError("assertion failed: " + show(msg))


@word("exit")
def _exit(vm):
    raise Exit(integer(vm.pop()))


@word("def")
def _def(vm):  # "name" [body] def
    body, name = quote(vm.pop()), string(vm.pop())
    vm.define(name, body.items, body.env)


@word("eval")
def _eval(vm):  # "source" eval
    vm.load(string(vm.pop()), "<eval>")


@word("include")
def _include(vm):  # "path" include
    path = string(vm.pop())
    if not os.path.isabs(path) and vm.cur is not None and vm.cur.pos:
        here = vm.cur.pos[0]
        if not here.startswith("<"):
            candidate = os.path.join(os.path.dirname(here), path)
            if os.path.exists(candidate):
                path = candidate
    with open(path, encoding="utf-8") as f:
        vm.load(f.read(), path)


# ------------------------------------------------------------------- types

@word("type")
def _type(vm):
    vm.push(type_name(vm.pop()))


@word("str")
def _str(vm):
    vm.push(show(vm.pop()))


@word("repr")
def _repr(vm):
    vm.push(repr_value(vm.pop()))


def _parse_number(s):
    s = s.strip().replace("_", "")
    try:
        return int(s, 0) if s[:2].lower() in ("0x", "0b", "0o") or s.lstrip("+-").isdigit() else float(s)
    except ValueError:
        return None


@word("num")
def _num(vm):  # str -- number|nil
    v = vm.pop()
    vm.push(v if type(v) in (int, float) else _parse_number(string(v)))


@word("int")
def _int(vm):
    v = vm.pop()
    t = type(v)
    if t is int:
        vm.push(v)
    elif t is float:
        vm.push(int(v))
    elif t is bool:
        vm.push(1 if v else 0)
    elif t is str:
        n = _parse_number(v)
        if n is None:
            raise CremaError(f"cannot convert {repr_value(v)} to int")
        vm.push(int(n))
    else:
        _fail("a number or string", v)


@word("float")
def _float(vm):
    v = vm.pop()
    if type(v) is str:
        n = _parse_number(v)
        if n is None:
            raise CremaError(f"cannot convert {repr_value(v)} to float")
        vm.push(float(n))
    else:
        vm.push(float(num(v)))


# ----------------------------------------------------------------- strings

@word("len")
def _len(vm):
    v = vm.pop()
    if type(v) in (str, list, dict):
        vm.push(len(v))
    else:
        vm.push(len(lst(v)))


@word("upper")
def _upper(vm):
    vm.push(string(vm.pop()).upper())


@word("lower")
def _lower(vm):
    vm.push(string(vm.pop()).lower())


@word("trim")
def _trim(vm):
    vm.push(string(vm.pop()).strip())


@word("split")
def _split(vm):  # str sep -- list
    sep, s = string(vm.pop()), string(vm.pop())
    vm.push(list(s) if sep == "" else s.split(sep))


@word("words")
def _words(vm):  # str -- list   (split on any whitespace)
    vm.push(string(vm.pop()).split())


@word("lines")
def _lines(vm):
    vm.push(string(vm.pop()).splitlines())


@word("join")
def _join(vm):  # list sep -- str
    sep, items = string(vm.pop()), lst(vm.pop())
    vm.push(sep.join(show(x) for x in items))


@word("chars")
def _chars(vm):
    vm.push(list(string(vm.pop())))


@word("ord")
def _ord(vm):
    s = string(vm.pop())
    if len(s) != 1:
        raise CremaError("ord expects a one-character string")
    vm.push(ord(s))


@word("chr")
def _chr(vm):
    vm.push(chr(integer(vm.pop())))


@word("replace")
def _replace(vm):  # str old new -- str
    new, old, s = string(vm.pop()), string(vm.pop()), string(vm.pop())
    vm.push(s.replace(old, new))


@word("starts-with?")
def _starts(vm):
    p, s = string(vm.pop()), string(vm.pop())
    vm.push(s.startswith(p))


@word("ends-with?")
def _ends(vm):
    p, s = string(vm.pop()), string(vm.pop())
    vm.push(s.endswith(p))


@word("format")
def _format(vm):  # "a={} b={}" {1 2} format
    args, fmt = lst(vm.pop()), string(vm.pop())
    out, i, k = [], 0, 0
    while i < len(fmt):
        if fmt.startswith("{{", i):
            out.append("{")
            i += 2
        elif fmt.startswith("}}", i):
            out.append("}")
            i += 2
        elif fmt.startswith("{}", i):
            if k >= len(args):
                raise CremaError("format: not enough values")
            out.append(show(args[k]))
            k += 1
            i += 2
        else:
            out.append(fmt[i])
            i += 1
    vm.push("".join(out))


# ------------------------------------------------------ lists, strs, dicts

@word("get")
def _get(vm):  # coll key -- value   (missing dict key gives nil)
    key, coll = vm.pop(), vm.pop()
    if type(coll) is dict:
        vm.push(coll.get(hashable(key)))
    else:
        seq = sequence(coll)
        vm.push(seq[_index(seq, key)])


@word("put")
def _put(vm):  # coll key value -- coll   (modifies coll)
    val, key, coll = vm.pop(), vm.pop(), vm.pop()
    if type(coll) is dict:
        coll[hashable(key)] = val
    elif type(coll) is list:
        coll[_index(coll, key)] = val
    else:
        _fail("a list or dict", coll)
    vm.push(coll)


@word("append")
def _append(vm):  # list x -- list   (modifies list)
    x, coll = vm.pop(), vm.pop()
    if type(coll) is not list:
        _fail("a list", coll)
    coll.append(x)
    vm.push(coll)


@word("pop")
def _pop(vm):  # list -- list x
    coll = vm.pop()
    if type(coll) is not list:
        _fail("a list", coll)
    if not coll:
        raise CremaError("pop from an empty list")
    x = coll.pop()
    vm.stack += [coll, x]


@word("insert")
def _insert(vm):  # list i x -- list
    x, i, coll = vm.pop(), integer(vm.pop()), vm.pop()
    if type(coll) is not list:
        _fail("a list", coll)
    coll.insert(i, x)
    vm.push(coll)


@word("remove")
def _remove(vm):  # coll key -- coll   (dict key or list index)
    key, coll = vm.pop(), vm.pop()
    if type(coll) is dict:
        coll.pop(hashable(key), None)
    elif type(coll) is list:
        del coll[_index(coll, key)]
    else:
        _fail("a list or dict", coll)
    vm.push(coll)


@word("slice")
def _slice(vm):  # seq start end -- seq   (end exclusive; negative counts from the end)
    end, start, seq = integer(vm.pop()), integer(vm.pop()), sequence(vm.pop())
    vm.push(seq[start:end])


@word("first")
def _first(vm):
    seq = sequence(vm.pop())
    vm.push(seq[_index(seq, 0)])


@word("last")
def _last(vm):
    seq = sequence(vm.pop())
    vm.push(seq[_index(seq, -1)])


@word("rest")
def _rest(vm):
    vm.push(sequence(vm.pop())[1:])


@word("reverse")
def _reverse(vm):
    vm.push(sequence(vm.pop())[::-1])


@word("sort")
def _sort(vm):
    import functools

    items = lst(vm.pop())
    vm.push(sorted(items, key=functools.cmp_to_key(lambda a, b: -1 if _less(a, b) else (1 if _less(b, a) else 0))))


@word("__sort-by-keys")
def _sort_by_keys(vm):  # keys items -- sorted-items
    import functools

    items, keys = lst(vm.pop()), lst(vm.pop())
    pairs = list(zip(keys, items))
    pairs.sort(key=functools.cmp_to_key(lambda a, b: -1 if _less(a[0], b[0]) else (1 if _less(b[0], a[0]) else 0)))
    vm.push([p[1] for p in pairs])


@word("range")
def _range(vm):  # start end -- list   (end exclusive)
    end, start = integer(vm.pop()), integer(vm.pop())
    vm.push(list(range(start, end)))


@word("copy")
def _copy(vm):
    v = vm.pop()
    vm.push(v.copy() if type(v) in (list, dict) else v)


@word("contains?")
def _contains(vm):  # coll x -- bool   (substring, element or dict key)
    x, coll = vm.pop(), vm.pop()
    t = type(coll)
    if t is str:
        vm.push(string(x) in coll)
    elif t is dict:
        vm.push(hashable(x) in coll)
    else:
        vm.push(any(equal(x, y) for y in lst(coll)))


@word("index-of")
def _index_of(vm):  # coll x -- i   (-1 when missing)
    x, coll = vm.pop(), vm.pop()
    if type(coll) is str:
        vm.push(coll.find(string(x)))
        return
    for i, y in enumerate(lst(coll)):
        if equal(x, y):
            vm.push(i)
            return
    vm.push(-1)


@word("empty?")
def _empty(vm):
    v = vm.pop()
    vm.push(len(v if type(v) in (str, list, dict) else lst(v)) == 0)


@word("unpack")
def _unpack(vm):  # list -- x1 x2 ...
    vm.stack += lst(vm.pop())


@word("pack")
def _pack(vm):  # x1 ... xn n -- list
    n = integer(vm.pop())
    if n < 0 or n > len(vm.stack):
        raise CremaError("stack underflow")
    items = vm.stack[len(vm.stack) - n:]
    del vm.stack[len(vm.stack) - n:]
    vm.push(items)


@word("dict")
def _dict(vm):
    vm.push({})


@word("keys")
def _keys(vm):
    vm.push(list(dct(vm.pop()).keys()))


@word("values")
def _values(vm):
    vm.push(list(dct(vm.pop()).values()))


# ---------------------------------------------------------------------- IO

def _write(vm, text):
    vm.stdout.write(text)


@word("print")
def _print(vm):
    _write(vm, show(vm.pop()))


@word("println", ".")
def _println(vm):
    _write(vm, show(vm.pop()) + "\n")


@word("cr")
def _cr(vm):
    _write(vm, "\n")


@word("eprintln")
def _eprintln(vm):
    sys.stderr.write(show(vm.pop()) + "\n")


@word("read-line")
def _read_line(vm):  # -- str|nil   (nil at end of input; newline removed)
    vm.stdout.flush()
    line = vm.stdin.readline()
    vm.push(line[:-1] if line.endswith("\n") else (line if line else None))


@word("read-stdin")
def _read_stdin(vm):
    vm.push(vm.stdin.read())


@word("read-file")
def _read_file(vm):  # path -- str
    with open(string(vm.pop()), encoding="utf-8") as f:
        vm.push(f.read())


@word("read-lines")
def _read_lines(vm):  # path -- list
    with open(string(vm.pop()), encoding="utf-8") as f:
        vm.push(f.read().splitlines())


@word("write-file")
def _write_file(vm):  # str path --
    path, text = string(vm.pop()), vm.pop()
    with open(path, "w", encoding="utf-8") as f:
        f.write(show(text))


@word("append-file")
def _append_file(vm):  # str path --
    path, text = string(vm.pop()), vm.pop()
    with open(path, "a", encoding="utf-8") as f:
        f.write(show(text))


@word("file-exists?")
def _file_exists(vm):
    vm.push(os.path.exists(string(vm.pop())))


@word("delete-file")
def _delete_file(vm):
    os.remove(string(vm.pop()))


@word("list-dir")
def _list_dir(vm):
    vm.push(sorted(os.listdir(string(vm.pop()))))


# ------------------------------------------------------------------ system

@word("args")
def _args(vm):
    vm.push(list(vm.argv))


@word("now")
def _now(vm):
    vm.push(time.time())


@word("getenv")
def _getenv(vm):
    vm.push(os.environ.get(string(vm.pop())))


@word("words-list")
def _words_list(vm):  # -- list of every callable word
    vm.push(sorted(set(vm.builtins) | set(vm.functions)))

