"""Optional real-world twin test; supply a rigged compressed/raw GLB pair.

Run locally with USDZ_FORGE_DRACO_COMPRESSED and USDZ_FORGE_DRACO_RAW set to
the corresponding delivery files. Client assets are deliberately not vendored.
"""

import os
import json
import struct

import numpy as np
import pytest
from pxr import Usd, UsdGeom, UsdSkel

from anim_probe import profile
from conftest import convert


def _max_nearest(left, right):
    """Directed point-set distance, robust to Draco's vertex reordering."""
    greatest = 0.0
    for start in range(0, len(left), 128):
        chunk = left[start:start + 128]
        squared = ((chunk[:, None, :] - right[None, :, :]) ** 2).sum(axis=2)
        greatest = max(greatest, float(np.sqrt(squared.min(axis=1).max())))
    return greatest


def _has_morph_targets(glb_path):
    with open(glb_path, 'rb') as handle:
        header = handle.read(20)
        size = struct.unpack_from('<I', header, 12)[0]
        gltf = json.loads(handle.read(size))
    return any(primitive.get('targets') for mesh in gltf.get('meshes', [])
               for primitive in mesh.get('primitives', []))


def test_rigged_draco_twin_matches_baked_skinning():
    compressed = os.environ.get('USDZ_FORGE_DRACO_COMPRESSED')
    raw = os.environ.get('USDZ_FORGE_DRACO_RAW')
    if not compressed or not raw:
        pytest.skip('provide corresponding rigged CCA GLB paths in the two environment variables')
    compressed_out, code, log = convert(compressed, 'cca_draco_pair_compressed')
    assert code == 0, log
    raw_out, code, log = convert(raw, 'cca_draco_pair_raw')
    assert code == 0, log

    compressed_profile, raw_profile = profile(compressed_out), profile(raw_out)
    assert compressed_profile['meshes'] == raw_profile['meshes']
    assert compressed_profile['skeletons'] == raw_profile['skeletons'] >= 1
    assert len(compressed_profile['skel_anims']) == len(raw_profile['skel_anims']) >= 1
    assert len(compressed_profile['blendshapes']) == len(raw_profile['blendshapes'])
    if _has_morph_targets(compressed):
        assert compressed_profile['blendshapes'], 'Draco input morph target was dropped'
    for compressed_anim, raw_anim in zip(compressed_profile['skel_anims'],
                                          raw_profile['skel_anims']):
        for key in ('joints', 'rot_samples', 'trans_samples',
                    'scale_samples', 'blend_weight_samples'):
            assert compressed_anim[key] == raw_anim[key]

    stages = [Usd.Stage.Open(path) for path in (compressed_out, raw_out)]
    if compressed_profile['blendshapes']:
        # A morph target's offsets must still correspond to the decoded base
        # positions, despite Draco potentially reordering/splitting vertices.
        morph_meshes = []
        for stage in stages:
            morph_meshes.append([
                UsdGeom.Mesh(prim) for prim in stage.Traverse()
                if prim.GetTypeName() == 'Mesh'
                and UsdSkel.BindingAPI(prim).GetBlendShapeTargetsRel().GetTargets()
            ])
        assert len(morph_meshes[0]) == len(morph_meshes[1])
        for left_mesh, right_mesh in zip(*morph_meshes):
            deformed = []
            for stage, mesh in zip(stages, (left_mesh, right_mesh)):
                points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float32).copy()
                shape_path = UsdSkel.BindingAPI(mesh).GetBlendShapeTargetsRel().GetTargets()[0]
                shape = UsdSkel.BlendShape(stage.GetPrimAtPath(shape_path))
                offsets = np.asarray(shape.GetOffsetsAttr().Get(), dtype=np.float32)
                indices = np.asarray(shape.GetPointIndicesAttr().Get(), dtype=np.int32)
                points[indices] += offsets
                deformed.append(points)
            assert _max_nearest(deformed[0], deformed[1]) < 2e-4
            assert _max_nearest(deformed[1], deformed[0]) < 2e-4
    for stage in stages:
        assert UsdSkel.BakeSkinning(stage.Traverse())
    meshes = [[UsdGeom.Mesh(prim) for prim in stage.Traverse()
               if prim.GetTypeName() == 'Mesh'] for stage in stages]
    assert [mesh.GetPrim().GetName() for mesh in meshes[0]] == [
        mesh.GetPrim().GetName() for mesh in meshes[1]]

    start = stages[0].GetStartTimeCode()
    end = stages[0].GetEndTimeCode()
    assert end > start
    assert (start, end) == (stages[1].GetStartTimeCode(),
                            stages[1].GetEndTimeCode())
    frames = (start, (start + end) / 2, end)
    moving_meshes = 0
    for compressed_mesh, raw_mesh in zip(*meshes):
        assert len(compressed_mesh.GetFaceVertexIndicesAttr().Get()) == len(
            raw_mesh.GetFaceVertexIndicesAttr().Get())
        if not compressed_mesh.GetPointsAttr().GetTimeSamples():
            continue
        if len(compressed_mesh.GetPointsAttr().Get()) < 500:
            continue
        moving_meshes += 1
        for frame in frames:
            left = np.asarray(compressed_mesh.GetPointsAttr().Get(frame),
                              dtype=np.float32)
            right = np.asarray(raw_mesh.GetPointsAttr().Get(frame),
                               dtype=np.float32)
            # Draco may split or reorder vertices. Compare posed point clouds
            # in both directions, not array order. The 2e-4 m bound is twice
            # the observed ~1.02e-4 m worst case on the bobcat CCA twin.
            assert _max_nearest(left, right) < 2e-4
            assert _max_nearest(right, left) < 2e-4
            assert np.max(np.abs(left.min(axis=0) - right.min(axis=0))) < 2e-4
            assert np.max(np.abs(left.max(axis=0) - right.max(axis=0))) < 2e-4
    assert moving_meshes > 0, 'pair did not exercise a skinned mesh'
