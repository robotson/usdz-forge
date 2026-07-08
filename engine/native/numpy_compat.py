"""Minimal numpy subset for usdStageWithGlTF on Python 2.7 without OpenSSL/numpy."""

from __future__ import division

import array
import struct


class _DType(object):
    def __init__(self, typecode, struct_fmt):
        self.typecode = typecode
        self.struct_fmt = struct_fmt

    def __repr__(self):
        return 'dtype(%r)' % self.typecode


uint8 = _DType('B', 'B')
int16 = _DType('h', 'h')
uint16 = _DType('H', 'H')
uint32 = _DType('I', 'I')
float32 = _DType('f', 'f')


class BufferArray(object):
    """Indexable buffer-backed array compatible with pxr attribute writers."""

    def __init__(self, typecode, items):
        self._array = array.array(typecode, items)

    def __getitem__(self, index):
        return self._array[index]

    def __len__(self):
        return len(self._array)

    def __iter__(self):
        return iter(self._array)

    def __repr__(self):
        return repr(self._array)


def _resolve_dtype(dtype):
    if isinstance(dtype, _DType):
        return dtype
    if dtype in (uint8, int16, uint16, uint32, float32):
        return dtype
    raise TypeError('unsupported dtype: %r' % (dtype,))


def frombuffer(buffer, dtype, count, offset=0):
    dtype = _resolve_dtype(dtype)
    if offset:
        segment = buffer[offset:offset + _byte_length(dtype, count)]
    else:
        segment = buffer[:_byte_length(dtype, count)]

    if dtype is uint8:
        return BufferArray('B', [ord(c) if isinstance(c, str) else c for c in segment])

    items = struct.unpack('<' + (dtype.struct_fmt * count), segment)
    return BufferArray(dtype.typecode, items)


def _byte_length(dtype, count):
    sizes = {'B': 1, 'h': 2, 'H': 2, 'I': 4, 'f': 4}
    return sizes[dtype.typecode] * count