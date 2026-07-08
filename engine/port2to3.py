#!/usr/bin/env python3
"""Mechanical Py2->Py3 porter for Apple's usdzconvert sources.

Handles exactly the relics present in these 2019 scripts:
  - xrange(            -> range(
  - .iteritems()       -> .items()   (and iterkeys/itervalues)
  - print >>stream, x  -> print(x, file=stream)
  - print X            -> print(X)    (with backslash-continuation preserved)

Everything else (pxr API, dict semantics) is already Py3-compatible. We run this
in place on the copied sources, then exercise the converter and fix any residue.
"""
import glob
import os
import re

NATIVE = os.path.join(os.path.dirname(__file__), "native")

# All Python sources, including the extension-less executable scripts.
FILES = sorted(set(
    glob.glob(os.path.join(NATIVE, "*.py")) + [
        os.path.join(NATIVE, name) for name in
        ("usdzconvert", "usdARKitChecker", "fixOpacity", "usdzcreateassetlib")
    ]
))


def convert_prints(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # A print *statement*: 'print ' at start (after indent), not 'print(' call.
        m = re.match(r"^(\s*)print\s+(.*)$", line)
        if m and not re.match(r"^\s*print\s*\(", line):
            indent, rest = m.group(1), m.group(2)
            # Join backslash line-continuations, preserving the backslash so any
            # continued string literal stays a single literal.
            while rest.endswith("\\"):
                i += 1
                rest = rest + "\n" + lines[i]
            chev = re.match(r"^>>\s*(\S+?)\s*,\s*(.*)$", rest, re.S)
            if chev:
                out.append("%sprint(%s, file=%s)" % (indent, chev.group(2), chev.group(1)))
            else:
                out.append("%sprint(%s)" % (indent, rest))
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def port(path):
    with open(path, "r") as fh:
        text = fh.read()
    original = text
    text = text.replace("xrange(", "range(")
    text = text.replace(".iteritems()", ".items()")
    text = text.replace(".iterkeys()", ".keys()")
    text = text.replace(".itervalues()", ".values()")
    text = convert_prints(text)
    if text != original:
        with open(path, "w") as fh:
            fh.write(text)
        return True
    return False


if __name__ == "__main__":
    for f in FILES:
        changed = port(f)
        print(("ported " if changed else "  ok   ") + os.path.basename(f))
