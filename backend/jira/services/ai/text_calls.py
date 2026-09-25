import json
import re

from .tools import TOOL_BY_NAME

MAX_CALLS = 5


class _PyParser:
    def __init__(self, s: str):
        self.s = s
        self.pos = 0

    def skip_ws(self):
        while self.pos < len(self.s) and self.s[self.pos].isspace():
            self.pos += 1

    def peek(self) -> str:
        return self.s[self.pos] if self.pos < len(self.s) else ''

    def parse_string(self):
        if self.pos >= len(self.s):
            return None
        quote = self.s[self.pos]
        if quote not in "'\"":
            return None
        self.pos += 1
        out = ''
        while self.pos < len(self.s):
            c = self.s[self.pos]
            self.pos += 1
            if c == quote:
                return out
            if c == '\\' and self.pos < len(self.s):
                e = self.s[self.pos]
                self.pos += 1
                if e == 'n':
                    out += '\n'
                elif e == 't':
                    out += '\t'
                elif e == 'r':
                    out += '\r'
                else:
                    out += e
            else:
                out += c
        return None  # unterminated

    def parse_number(self):
        m = re.match(r'-?\d+(\.\d+)?', self.s[self.pos:])
        if not m:
            return None
        self.pos += len(m.group(0))
        return float(m.group(0)) if '.' in m.group(0) else int(m.group(0))

    def parse_ident_value(self):
        m = re.match(r'[A-Za-z_]\w*', self.s[self.pos:])
        if not m:
            return (False, None)
        word = m.group(0)
        if word in ('True', 'true'):
            self.pos += len(word)
            return (True, True)
        if word in ('False', 'false'):
            self.pos += len(word)
            return (True, False)
        if word in ('None', 'null'):
            self.pos += len(word)
            return (True, None)
        return (False, None)

    def parse_value(self):
        self.skip_ws()
        c = self.peek()
        if c in ("'", '"'):
            v = self.parse_string()
            return (v is not None, v)
        if c == '[':
            self.pos += 1
            items = []
            while True:
                self.skip_ws()
                if self.peek() == ']':
                    self.pos += 1
                    return (True, items)
                ok, item = self.parse_value()
                if not ok:
                    return (False, None)
                items.append(item)
                self.skip_ws()
                if self.peek() == ',':
                    self.pos += 1
                    continue
                if self.peek() == ']':
                    self.pos += 1
                    return (True, items)
                return (False, None)
        num = self.parse_number()
        if num is not None:
            return (True, num)
        return self.parse_ident_value()

    def parse_call_args(self, name: str):
        """Parse `name(kw='x', 1, ...)` starting at the '('; returns kwargs dict or None."""
        if self.peek() != '(':
            return None
        self.pos += 1
        kwargs = {}
        positional = []
        while True:
            self.skip_ws()
            if self.peek() == ')':
                self.pos += 1
                break
            if self.pos >= len(self.s):
                return None
            kw = re.match(r'([A-Za-z_]\w*)\s*=', self.s[self.pos:])
            # exclude '==' accidentally consumed
            if kw and self.s[self.pos + len(kw.group(0)) - 1] == '=' \
                    and self.s[self.pos + len(kw.group(0))] != '=':
                self.pos += len(kw.group(0))
                ok, v = self.parse_value()
                if not ok:
                    return None
                kwargs[kw.group(1)] = v
            else:
                ok, v = self.parse_value()
                if not ok:
                    return None
                positional.append(v)
            self.skip_ws()
            if self.peek() == ',':
                self.pos += 1
                continue
            if self.peek() == ')':
                self.pos += 1
                break
            return None
        if positional:
            required = (TOOL_BY_NAME.get(name) or {}).get('parameters', {}).get('required', [])
            if len(positional) > len(required):
                return None
            for i, v in enumerate(positional):
                if required[i] not in kwargs:
                    kwargs[required[i]] = v
        return kwargs


# ---------- JSON-style parsing ----------

def _parse_args_field(a) -> dict:
    if isinstance(a, str):
        try:
            p = json.loads(a)
            return p if isinstance(p, dict) else {}
        except Exception:
            return {}
    return a if isinstance(a, dict) else {}


def _normalize_json_calls(v, out: list):
    if v is None:
        return
    if isinstance(v, list):
        for item in v:
            _normalize_json_calls(item, out)
        return
    if not isinstance(v, dict):
        return
    if isinstance(v.get('tool_calls'), list):
        _normalize_json_calls(v['tool_calls'], out)
        return
    if isinstance(v.get('function'), dict) and isinstance(v['function'].get('name'), str):
        out.append({'name': v['function']['name'], 'args': _parse_args_field(v['function'].get('arguments'))})
        return
    if isinstance(v.get('name'), str):
        out.append({'name': v['name'],
                    'args': _parse_args_field(v.get('arguments') if v.get('arguments') is not None
                                              else (v.get('args') if v.get('args') is not None else v.get('parameters')))})
        return
    if isinstance(v.get('tool'), str):
        out.append({'name': v['tool'], 'args': _parse_args_field(v.get('arguments') if v.get('arguments') is not None else v.get('args'))})


def _balanced_end(s: str, i: int) -> int:
    open_ch = s[i]
    close_ch = '}' if open_ch == '{' else ']'
    depth = 0
    in_str = False
    str_ch = ''
    j = i
    while j < len(s):
        c = s[j]
        if in_str:
            if c == '\\':
                j += 1
            elif c == str_ch:
                in_str = False
        elif c in '"\'':
            in_str = True
            str_ch = c
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _scan_bare_json(text: str, push):
    i = 0
    while i < len(text):
        c = text[i]
        if c not in '{[':
            i += 1
            continue
        end = _balanced_end(text, i)
        if end == -1:
            i += 1
            continue
        try:
            parsed = json.loads(text[i:end + 1])
            calls = []
            _normalize_json_calls(parsed, calls)
            for call in calls:
                push(call['name'], call['args'])
            if calls:
                i = end  # consumed; don't rescan inside
        except Exception:
            pass
        i += 1


def parse_text_tool_calls(content: str, allowed_tool_names) -> list:
    allowed = set(allowed_tool_names)
    calls = []
    seen = set()

    def push(name, args):
        if len(calls) >= MAX_CALLS:
            return
        if name not in allowed:
            return
        fp = f'{name}::{json.dumps(args if args is not None else {})}'
        if fp in seen:
            return
        seen.add(fp)
        calls.append({'name': name, 'args': args if isinstance(args, dict) else {}})

    for m in re.finditer(r'<tool_call>([\s\S]*?)</tool_call>', content, re.IGNORECASE):
        _scan_bare_json(m.group(1), push)
    for m in re.finditer(r'```(?:json)\s*\n?([\s\S]*?)```', content, re.IGNORECASE):
        _scan_bare_json(m.group(1), push)
    _scan_bare_json(content, push)

    if allowed:
        name_re = re.compile(r'\b(' + '|'.join(re.escape(n) for n in allowed) + r')\s*\(')
        for m in name_re.finditer(content):
            open_idx = m.end() - 1
            parser = _PyParser(content)
            parser.pos = open_idx
            args = parser.parse_call_args(m.group(1))
            if args is not None:
                push(m.group(1), args)

    return calls
