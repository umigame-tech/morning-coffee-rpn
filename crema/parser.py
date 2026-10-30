"""Tokenizer and parser for Crema source code."""

import re

from .values import Bind, Collect, Definition, ParseError, QuoteLit, Word

_INT_RE = re.compile(r"[+-]?\d+\Z")
_HEX_RE = re.compile(r"[+-]?0[xX][0-9a-fA-F]+\Z")
_FLOAT_RE = re.compile(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?\Z")
_LITERALS = {"true": True, "false": False, "nil": None}
_STRING_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0", "e": "\x1b"}
_DELIMS = "[]{}"


class Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind, value, pos):
        self.kind = kind  # "word", "lit", "[", "]", "{", "#{", "}"
        self.value = value
        self.pos = pos


def _classify(text):
    if text in _LITERALS:
        return _LITERALS[text]
    if _INT_RE.match(text):
        return int(text)
    if _HEX_RE.match(text):
        return int(text, 16)
    if _FLOAT_RE.match(text):
        return float(text)
    raise ValueError


def tokenize(src, file="<input>"):
    tokens = []
    i, n = 0, len(src)
    line, line_start = 1, 0
    while i < n:
        c = src[i]
        if c == "\n":
            i += 1
            line, line_start = line + 1, i
            continue
        if c.isspace():
            i += 1
            continue
        pos = (file, line, i - line_start + 1)

        if c == "#":
            if src.startswith("#{", i):
                tokens.append(Token("#{", None, pos))
                i += 2
                continue
            while i < n and src[i] != "\n":
                i += 1
            continue

        if c == "(" and (i + 1 == n or src[i + 1].isspace()):
            # ( stack effect comment )
            j = i + 1
            while j < n and not (src[j] == ")" and src[j - 1].isspace()):
                j += 1
            if j >= n:
                raise ParseError("unterminated ( comment", pos, incomplete=True)
            for k in range(i, j):
                if src[k] == "\n":
                    line, line_start = line + 1, k + 1
            i = j + 1
            continue

        if c == '"':
            buf = []
            i += 1
            while True:
                if i >= n:
                    raise ParseError("unterminated string", pos, incomplete=True)
                ch = src[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    if i + 1 >= n:
                        raise ParseError("unterminated string", pos, incomplete=True)
                    esc = src[i + 1]
                    if esc in _STRING_ESCAPES:
                        buf.append(_STRING_ESCAPES[esc])
                        i += 2
                    elif esc == "u" and src.startswith("{", i + 2):
                        end = src.find("}", i + 3)
                        if end < 0:
                            raise ParseError("bad \\u{...} escape", pos)
                        try:
                            buf.append(chr(int(src[i + 3:end], 16)))
                        except ValueError:
                            raise ParseError("bad \\u{...} escape", pos)
                        i = end + 1
                    else:
                        raise ParseError(f"unknown escape \\{esc}", (file, line, i - line_start + 1))
                    continue
                if ch == "\n":
                    line, line_start = line + 1, i + 1
                buf.append(ch)
                i += 1
            tokens.append(Token("lit", "".join(buf), pos))
            continue

        if c in _DELIMS:
            tokens.append(Token(c, None, pos))
            i += 1
            continue

        j = i
        while j < n and not src[j].isspace() and src[j] not in _DELIMS:
            j += 1
        text = src[i:j]
        i = j
        try:
            tokens.append(Token("lit", _classify(text), pos))
        except ValueError:
            tokens.append(Token("word", text, pos))
    return tokens


_CLOSERS = {"[": "]", "{": "}", "#{": "}"}


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.defs = []

    def next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def seq(self, closer, opener_pos, top=False):
        """Parse items until `closer` (a bracket, ";" for definitions, or None for EOF)."""
        items = []
        while True:
            if self.i >= len(self.tokens):
                if closer is None:
                    return items
                what = "';' to end the definition" if closer == ";" else f"'{closer}'"
                raise ParseError(f"expected {what} before end of input", opener_pos, incomplete=True)
            tok = self.next()
            kind = tok.kind
            if kind == "lit":
                items.append(tok.value)
            elif kind == "word":
                name = tok.value
                if name == ":":
                    if not top:
                        raise ParseError("definitions (':') are only allowed at the top level", tok.pos)
                    self.definition(tok)
                elif name == ";":
                    if closer != ";":
                        raise ParseError("unexpected ';'", tok.pos)
                    return items
                elif name == "->":
                    if self.i >= len(self.tokens):
                        raise ParseError("expected a variable name after '->'", tok.pos, incomplete=True)
                    target = self.next()
                    if target.kind != "word" or target.value in (":", ";", "->"):
                        raise ParseError("expected a variable name after '->'", target.pos)
                    items.append(Bind(target.value, tok.pos))
                else:
                    items.append(Word(name, tok.pos))
            elif kind in _CLOSERS:
                body = self.seq(_CLOSERS[kind], tok.pos)
                if kind == "[":
                    items.append(QuoteLit(body, tok.pos))
                else:
                    items.append(Collect(body, kind == "#{", tok.pos))
            else:  # a closing bracket
                if kind != closer:
                    raise ParseError(f"unexpected '{kind}'", tok.pos)
                return items

    def definition(self, colon):
        if self.i >= len(self.tokens):
            raise ParseError("expected a name after ':'", colon.pos, incomplete=True)
        name = self.next()
        if name.kind != "word" or name.value in (":", ";", "->"):
            raise ParseError("expected a name after ':'", name.pos)
        body = self.seq(";", colon.pos)
        self.defs.append(Definition(name.value, body, colon.pos))


def parse(src, file="<input>"):
    """Return (definitions, top-level code) for a source string."""
    p = _Parser(tokenize(src, file))
    code = p.seq(None, None, top=True)
    return p.defs, code
