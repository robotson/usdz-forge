"""Bootstrap USD/python paths for subprocesses launched without PYTHONPATH."""
from __future__ import print_function

import os
import sys


class _FilteredStderr(object):
    """Hide harmless hashlib/OpenSSL noise that can confuse GUI subprocess checks."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        if not data:
            return
        if 'unsupported hash type' in data:
            return
        if 'code for hash' in data and 'was not found' in data:
            return
        self._stream.write(data)

    def flush(self):
        self._stream.flush()


sys.stderr = _FilteredStderr(sys.stderr)


def setup():
    base = os.path.dirname(os.path.abspath(__file__))
    usd_lib = os.path.normpath(os.path.join(base, '..', 'USD', 'lib'))
    usd_py = os.path.join(usd_lib, 'python')

    if usd_py not in sys.path:
        sys.path.insert(0, usd_py)
    if base not in sys.path:
        sys.path.insert(0, base)

    # Helpful for diagnostics; dyld loads at process start so this may not
    # affect .so loading, but @loader_path patches handle that.
    existing = os.environ.get('DYLD_LIBRARY_PATH', '')
    if usd_lib not in existing.split(':'):
        os.environ['DYLD_LIBRARY_PATH'] = usd_lib + (':' + existing if existing else '')

    existing_pp = os.environ.get('PYTHONPATH', '')
    if usd_py not in existing_pp.split(':'):
        os.environ['PYTHONPATH'] = usd_py + (':' + existing_pp if existing_pp else '')


setup()