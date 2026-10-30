"""Runtime values, code nodes and value formatting for Crema."""


class CremaError(Exception):
    """An error raised while parsing or running a Crema program."""

    def __init__(self, message, pos=None):
        super().__init__(message)
        self.message = message
        self.pos = pos  # (file, line, col) or None
        self.trace = []  # names of the functions active when the error happened

    def located(self):
        if self.pos is None:
            return self.message
        file, line, col = self.pos
        return f"{file}:{line}:{col}: {self.message}"


class ParseError(CremaError):
    def __init__(self, message, pos=None, incomplete=False):
        super().__init__(message, pos)
        self.incomplete = incomplete  # True when more input could fix it (REPL)


# ---------------------------------------------------------------- code nodes

class Word:
    """A word reference in code. Also appears as data when a quote is inspected."""

    __slots__ = ("name", "pos")

    def __init__(self, name, pos=None):
        self.name = name
        self.pos = pos

    def __repr__(self):
        return self.name


class QuoteLit:
    """`[ ... ]` in source. Becomes a Quote (closure) when executed."""

    __slots__ = ("items", "pos")

    def __init__(self, items, pos=None):
        self.items = items
        self.pos = pos


class Collect:
    """`{ ... }` or `#{ ... }`: run the body and gather pushed values."""

    __slots__ = ("items", "is_dict", "pos")

    def __init__(self, items, is_dict, pos=None):
        self.items = items
        self.is_dict = is_dict
        self.pos = pos


class Bind:
    """`-> name`: pop the top of the stack into a variable."""

    __slots__ = ("name", "pos")

    def __init__(self, name, pos=None):
        self.name = name
        self.pos = pos


class Definition:
    """`: name ... ;` at the top level of a source file."""

    __slots__ = ("name", "body", "pos")

    def __init__(self, name, body, pos=None):
        self.name = name
        self.body = body
        self.pos = pos


# ------------------------------------------------------------ runtime values

class Env:
    """Variable scope. One per function call; the root one holds globals."""

    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent


class Quote:
    """A block of code together with the scope it was created in."""

    __slots__ = ("items", "env")

    def __init__(self, items, env):
        self.items = items
        self.env = env


class Function:
    __slots__ = ("name", "body", "env", "pos")

    def __init__(self, name, body, env, pos=None):
        self.name = name
        self.body = body
        self.env = env
        self.pos = pos


# ---------------------------------------------------------------- formatting

def type_name(v):
    if v is None:
        return "nil"
    t = type(v)
    if t is bool:
        return "bool"
    if t is int:
        return "int"
    if t is float:
        return "float"
    if t is str:
        return "str"
    if t is list:
        return "list"
    if t is dict:
        return "dict"
    if t is Quote:
        return "quote"
    if t is Word:
        return "word"
    return "code"


_ESCAPES = {"\n": "\\n", "\t": "\\t", "\r": "\\r", '"': '\\"', "\\": "\\\\", "\0": "\\0"}


def repr_value(v):
    """Source-like representation: strings are quoted."""
    if type(v) is str:
        return '"' + "".join(_ESCAPES.get(c, c) for c in v) + '"'
    return show(v)


def show(v):
    """Human-readable representation used by `print`."""
    if v is None:
        return "nil"
    if v is True:
        return "true"
    if v is False:
        return "false"
    t = type(v)
    if t is str:
        return v
    if t is int:
        return str(v)
    if t is float:
        if v != v:
            return "nan"
        if v in (float("inf"), float("-inf")):
            return "inf" if v > 0 else "-inf"
        return repr(v)
    if t is list:
        return "{" + " ".join(repr_value(x) for x in v) + "}"
    if t is dict:
        return "#{" + " ".join(repr_value(k) + " " + repr_value(x) for k, x in v.items()) + "}"
    if t is Quote:
        return "[" + " ".join(repr_code(x) for x in v.items) + "]"
    return repr_code(v)


def repr_code(node):
    t = type(node)
    if t is Word:
        return node.name
    if t is QuoteLit:
        return "[" + " ".join(repr_code(x) for x in node.items) + "]"
    if t is Collect:
        return ("#{" if node.is_dict else "{") + " ".join(repr_code(x) for x in node.items) + "}"
    if t is Bind:
        return "-> " + node.name
    return repr_value(node)


def quote_items_as_data(q):
    """Items of a quote seen as data: `[1 2 "a"]` behaves like a list."""
    out = []
    for item in q.items:
        if type(item) is QuoteLit:
            out.append(Quote(item.items, q.env))
        else:
            out.append(item)
    return out


def equal(a, b):
    ta, tb = type(a), type(b)
    if ta is bool or tb is bool:
        return ta is tb and a == b
    if ta in (int, float) and tb in (int, float):
        return a == b
    if ta is not tb:
        return False
    if ta is list:
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if ta is dict:
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if ta is Quote:
        return a is b or show(a) == show(b)
    if ta is Word:
        return a.name == b.name
    return a == b


def truthy(v):
    """Only `false` and `nil` are falsy."""
    return v is not False and v is not None
