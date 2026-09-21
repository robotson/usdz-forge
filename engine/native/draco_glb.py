"""Expand Draco-compressed GLB primitives before the USD glTF reader sees them.

Google's pinned Draco WebAssembly decoder runs in macOS JavaScriptCore. The
decoder and its JavaScript glue are vendored; no Node, compiler, or Python
dependency is needed at install or conversion time.
"""

import copy
import ctypes
import json
import os
import struct


EXTENSION = 'KHR_draco_mesh_compression'
VENDOR_DIR = os.path.join(os.path.dirname(__file__), 'vendor', 'draco')
COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
DATA_TYPES = {
    5120: ('DT_INT8', 1, 'b'),
    5121: ('DT_UINT8', 1, 'B'),
    5122: ('DT_INT16', 2, 'h'),
    5123: ('DT_UINT16', 2, 'H'),
    5125: ('DT_UINT32', 4, 'I'),
    5126: ('DT_FLOAT32', 4, 'f'),
}


class DracoDecodeError(Exception):
    pass


class JavaScriptCore:
    """Small, private bridge for byte arrays and script evaluation."""

    def __init__(self, wasm_path, wrapper_path):
        try:
            self.lib = ctypes.CDLL(
                '/System/Library/Frameworks/JavaScriptCore.framework/JavaScriptCore')
            self._bind()
            self.ctx = self.create_context(None)
            self._buffers = []  # JS typed arrays refer to these Python buffers.
            self.set_bytes('wasmInputData', open(wasm_path, 'rb').read())
            with open(wrapper_path, encoding='utf-8') as handle:
                self.eval(handle.read())
            self.eval('''
                var dracoModuleState = 'pending';
                var dracoModuleError = '';
                DracoDecoderModule({
                  wasmBinary: wasmInputData,
                  instantiateWasm: function(imports, receive) {
                    var wasmModule = new WebAssembly.Module(wasmInputData);
                    var instance = new WebAssembly.Instance(wasmModule, imports);
                    receive(instance, wasmModule);
                    return instance.exports;
                  }
                }).then(function(m) {
                  globalThis.dracoModule = m;
                  dracoModuleState = 'ready';
                }, function(e) {
                  dracoModuleError = String(e);
                  dracoModuleState = 'error';
                });
            ''')
            state = self.text('dracoModuleState')
            if state != 'ready':
                raise DracoDecodeError('decoder initialization: ' +
                                       self.text('dracoModuleError || dracoModuleState'))
        except (OSError, ValueError) as exc:
            raise DracoDecodeError('decoder unavailable: ' + str(exc)) from exc

    def _bind(self):
        def bind(name, result, args):
            fn = getattr(self.lib, name)
            fn.restype = result
            fn.argtypes = args
            return fn

        ptr = ctypes.c_void_p
        self.create_context = bind('JSGlobalContextCreate', ptr, [ptr])
        self.release_context = bind('JSGlobalContextRelease', None, [ptr])
        self.make_string = bind('JSStringCreateWithUTF8CString', ptr, [ctypes.c_char_p])
        self.release_string = bind('JSStringRelease', None, [ptr])
        self.evaluate = bind('JSEvaluateScript', ptr,
                             [ptr, ptr, ptr, ptr, ctypes.c_int, ctypes.POINTER(ptr)])
        self.to_string = bind('JSValueToStringCopy', ptr,
                              [ptr, ptr, ctypes.POINTER(ptr)])
        self.max_string_size = bind('JSStringGetMaximumUTF8CStringSize', ctypes.c_size_t,
                                    [ptr])
        self.get_utf8 = bind('JSStringGetUTF8CString', ctypes.c_size_t,
                             [ptr, ptr, ctypes.c_size_t])
        self.make_typed_array = bind('JSObjectMakeTypedArrayWithBytesNoCopy', ptr,
                                     [ptr, ctypes.c_int, ptr, ctypes.c_size_t,
                                      ptr, ptr, ctypes.POINTER(ptr)])
        self.global_object = bind('JSContextGetGlobalObject', ptr, [ptr])
        self.set_property = bind('JSObjectSetProperty', None,
                                 [ptr, ptr, ptr, ptr, ctypes.c_uint, ctypes.POINTER(ptr)])
        self.typed_ptr = bind('JSObjectGetTypedArrayBytesPtr', ptr,
                              [ptr, ptr, ctypes.POINTER(ptr)])
        self.typed_length = bind('JSObjectGetTypedArrayByteLength', ctypes.c_size_t,
                                 [ptr, ptr, ctypes.POINTER(ptr)])

    def _string(self, value):
        error = ctypes.c_void_p()
        js_string = self.to_string(self.ctx, value, ctypes.byref(error))
        if not js_string:
            return '<JavaScript value unavailable>'
        try:
            result = ctypes.create_string_buffer(self.max_string_size(js_string))
            self.get_utf8(js_string, result, len(result))
            return result.value.decode('utf-8', errors='replace')
        finally:
            self.release_string(js_string)

    def eval(self, source):
        js_source = self.make_string(source.encode('utf-8'))
        try:
            error = ctypes.c_void_p()
            value = self.evaluate(self.ctx, js_source, None, None, 0,
                                  ctypes.byref(error))
            if error.value:
                raise DracoDecodeError(self._string(error))
            return value
        finally:
            self.release_string(js_source)

    def text(self, source):
        return self._string(self.eval(source))

    def json(self, source):
        return json.loads(self.text('JSON.stringify(' + source + ')'))

    def set_bytes(self, name, data):
        # JSTypedArrayType enum value 3 is Uint8Array (JSValueRef.h).
        buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        self._buffers.append(buffer)
        error = ctypes.c_void_p()
        value = self.make_typed_array(self.ctx, 3, ctypes.byref(buffer), len(data),
                                      None, None, ctypes.byref(error))
        if error.value or not value:
            raise DracoDecodeError('could not pass bytes to JavaScriptCore')
        js_name = self.make_string(name.encode('utf-8'))
        try:
            self.set_property(self.ctx, self.global_object(self.ctx), js_name,
                              value, 0, ctypes.byref(error))
            if error.value:
                raise DracoDecodeError('could not set JavaScriptCore input')
        finally:
            self.release_string(js_name)

    def bytes(self, source):
        value = self.eval('globalThis.dracoOutput = (' + source + ')')
        error = ctypes.c_void_p()
        pointer = self.typed_ptr(self.ctx, value, ctypes.byref(error))
        length = self.typed_length(self.ctx, value, ctypes.byref(error))
        if error.value or (not pointer and length):
            raise DracoDecodeError('could not retrieve decoded bytes')
        return ctypes.string_at(pointer, length) if length else b''

    def close(self):
        if getattr(self, 'ctx', None):
            self.release_context(self.ctx)
            self.ctx = None
        self._buffers.clear()


class DracoDecoder:
    def __init__(self, vendor_dir=VENDOR_DIR):
        self.js = JavaScriptCore(os.path.join(vendor_dir, 'draco_decoder.wasm'),
                                 os.path.join(vendor_dir, 'draco_wasm_wrapper.js'))

    def close(self):
        self.js.close()

    def decode(self, compressed, attributes):
        """Return (indices as uint32 bytes, decoded attributes, point count)."""
        self.js.set_bytes('dracoInput', compressed)
        state = self.js.json('''(function() {
            globalThis.dracoDecoder = new dracoModule.Decoder();
            globalThis.dracoBuffer = new dracoModule.DecoderBuffer();
            dracoBuffer.Init(dracoInput, dracoInput.length);
            globalThis.dracoMesh = new dracoModule.Mesh();
            var status = dracoDecoder.DecodeBufferToMesh(dracoBuffer, dracoMesh);
            return {ok: status.ok(), message: status.error_msg(),
                    points: dracoMesh.num_points(), faces: dracoMesh.num_faces()};
        })()''')
        if not state['ok']:
            raise DracoDecodeError('Draco decode: ' + state['message'])
        indices = self.js.bytes('''(function() {
            var length = dracoMesh.num_faces() * 12;
            var ptr = dracoModule._malloc(length);
            try {
              if (!dracoDecoder.GetTrianglesUInt32Array(dracoMesh, length, ptr))
                throw new Error('index decode failed');
              return dracoModule.HEAPU8.slice(ptr, ptr + length);
            } finally { dracoModule._free(ptr); }
        })()''')
        decoded = {}
        for semantic, spec in attributes.items():
            draco_id, component_type, accessor_type = spec
            if component_type not in DATA_TYPES or accessor_type not in COMPONENTS:
                raise DracoDecodeError('unsupported accessor for ' + semantic)
            dtype, size, _ = DATA_TYPES[component_type]
            metadata = self.js.json('''(function() {
                var attr = dracoDecoder.GetAttributeByUniqueId(dracoMesh, %d);
                if (!attr || !attr.ptr) return null;
                return {components:attr.num_components()};
            })()''' % draco_id)
            if metadata is None or metadata['components'] != COMPONENTS[accessor_type]:
                raise DracoDecodeError('Draco attribute mismatch: ' + semantic)
            length = state['points'] * metadata['components'] * size
            decoded[semantic] = self.js.bytes('''(function() {
                var attr = dracoDecoder.GetAttributeByUniqueId(dracoMesh, %d);
                var length = %d;
                var ptr = dracoModule._malloc(length);
                try {
                  if (!dracoDecoder.GetAttributeDataArrayForAllPoints(
                      dracoMesh, attr, dracoModule.%s, length, ptr))
                    throw new Error('attribute decode failed');
                  return dracoModule.HEAPU8.slice(ptr, ptr + length);
                } finally { dracoModule._free(ptr); }
            })()''' % (draco_id, length, dtype))
        self.js.eval('''dracoModule.destroy(dracoMesh);
                        dracoModule.destroy(dracoBuffer);
                        dracoModule.destroy(dracoDecoder);''')
        return indices, decoded, state['points']


def _read_glb(path):
    with open(path, 'rb') as handle:
        data = handle.read()
    if len(data) < 20 or data[:4] != b'glTF':
        raise DracoDecodeError('invalid GLB header')
    _, version, length = struct.unpack_from('<4sII', data)
    if version != 2 or length != len(data):
        raise DracoDecodeError('invalid GLB length or version')
    chunks = []
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise DracoDecodeError('truncated GLB chunk')
        size, kind = struct.unpack_from('<I4s', data, offset)
        offset += 8
        chunks.append((kind, data[offset:offset + size]))
        offset += size
    if offset != len(data) or not chunks or chunks[0][0] != b'JSON':
        raise DracoDecodeError('GLB JSON chunk unavailable')
    if len(chunks) == 1:
        return json.loads(chunks[0][1]), bytearray(), []
    if chunks[1][0] != b'BIN\0':
        raise DracoDecodeError('GLB BIN chunk unavailable')
    return json.loads(chunks[0][1]), bytearray(chunks[1][1]), chunks[2:]


def _append_view(gltf, binary, data):
    binary.extend(b'\0' * (-len(binary) % 4))
    offset = len(binary)
    binary.extend(data)
    gltf.setdefault('bufferViews', []).append({
        'buffer': 0, 'byteOffset': offset, 'byteLength': len(data)})
    return len(gltf['bufferViews']) - 1


def _new_accessor(gltf, original, view, count, component_type=None):
    accessor = copy.deepcopy(original)
    accessor['bufferView'] = view
    accessor['byteOffset'] = 0
    accessor['count'] = count
    if component_type is not None:
        accessor['componentType'] = component_type
    accessor.pop('sparse', None)
    accessor.pop('min', None)
    accessor.pop('max', None)
    gltf['accessors'].append(accessor)
    return len(gltf['accessors']) - 1


def _position_bounds(data):
    minimum = [float('inf')] * 3
    maximum = [float('-inf')] * 3
    for vertex in struct.iter_unpack('<fff', data):
        for axis, value in enumerate(vertex):
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
    return minimum, maximum


def _pack_indices(raw, component_type):
    count = len(raw) // 4
    values = struct.unpack('<%dI' % count, raw)
    if component_type not in (5121, 5123, 5125):
        component_type = 5125
    maximum = {5121: 255, 5123: 65535, 5125: 0xffffffff}[component_type]
    if values and max(values) > maximum:
        component_type = 5125
    fmt = {5121: 'B', 5123: 'H', 5125: 'I'}[component_type]
    return struct.pack('<%d%s' % (count, fmt), *values), component_type


def maybe_expand_draco(src_path, dst_path, vendor_dir=VENDOR_DIR):
    """Write a normal GLB to dst_path; return False if the input has no Draco."""
    gltf, binary, extra_chunks = _read_glb(src_path)
    compressed_primitives = [
        primitive
        for mesh in gltf.get('meshes', [])
        for primitive in mesh.get('primitives', [])
        if EXTENSION in primitive.get('extensions', {})]
    if not compressed_primitives:
        return False
    if os.environ.get('USDZ_FORGE_DRACO_DISABLE') == '1':
        raise DracoDecodeError('decoder disabled')
    decoder = DracoDecoder(vendor_dir)
    try:
        for primitive in compressed_primitives:
            extension = primitive['extensions'][EXTENSION]
            view = gltf['bufferViews'][extension['bufferView']]
            if view.get('buffer', 0) != 0:
                raise DracoDecodeError('Draco payload is not in the GLB buffer')
            start = view.get('byteOffset', 0)
            payload = bytes(binary[start:start + view['byteLength']])
            if len(payload) != view['byteLength']:
                raise DracoDecodeError('truncated Draco payload')
            specs = {}
            for semantic, draco_id in extension['attributes'].items():
                if semantic not in primitive['attributes']:
                    raise DracoDecodeError('missing accessor: ' + semantic)
                original = gltf['accessors'][primitive['attributes'][semantic]]
                if semantic == 'POSITION' and (original['componentType'] != 5126 or
                                               original['type'] != 'VEC3'):
                    raise DracoDecodeError('unsupported POSITION accessor')
                specs[semantic] = (draco_id, original['componentType'], original['type'])
            indices, attrs, points = decoder.decode(payload, specs)
            for semantic, data in attrs.items():
                old_index = primitive['attributes'][semantic]
                accessor = gltf['accessors'][old_index]
                new_index = _new_accessor(gltf, accessor,
                                          _append_view(gltf, binary, data), points)
                if semantic == 'POSITION' and points:
                    minimum, maximum = _position_bounds(data)
                    gltf['accessors'][new_index]['min'] = minimum
                    gltf['accessors'][new_index]['max'] = maximum
                primitive['attributes'][semantic] = new_index
            old_index = primitive.get('indices')
            original = (gltf['accessors'][old_index] if old_index is not None else
                        {'type': 'SCALAR', 'componentType': 5125})
            packed, dtype = _pack_indices(indices, original['componentType'])
            primitive['indices'] = _new_accessor(
                gltf, original, _append_view(gltf, binary, packed),
                len(indices) // 4, dtype)
            del primitive['extensions'][EXTENSION]
            if not primitive['extensions']:
                del primitive['extensions']
        for key in ('extensionsUsed', 'extensionsRequired'):
            if key in gltf:
                gltf[key] = [name for name in gltf[key] if name != EXTENSION]
                if not gltf[key]:
                    del gltf[key]
        gltf['buffers'][0]['byteLength'] = len(binary)
        json_data = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
        json_data += b' ' * (-len(json_data) % 4)
        binary.extend(b'\0' * (-len(binary) % 4))
        chunks = [(b'JSON', json_data), (b'BIN\0', bytes(binary))] + extra_chunks
        total = 12 + sum(8 + len(data) for _, data in chunks)
        with open(dst_path, 'wb') as handle:
            handle.write(struct.pack('<4sII', b'glTF', 2, total))
            for kind, data in chunks:
                handle.write(struct.pack('<I4s', len(data), kind))
                handle.write(data)
        return True
    finally:
        decoder.close()
