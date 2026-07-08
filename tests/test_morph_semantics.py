"""Tier-2 semantic validation harness for morph/blendshape conversion (A2).

glTF morphing is exactly defined: deformed(t) = base + sum_i(w_i(t) * target_i).
This test computes expected vertex positions INDEPENDENTLY from the raw GLB
bytes, then reads what the converter authored into USD (base points, BlendShape
offsets, the blendShapeWeights curve) and verifies the math matches at every
authored keyframe. No renderer involved — pure conversion semantics.

Written BEFORE the implementation (test-first): it auto-skips while the
converter authors no BlendShape prims, and becomes the acceptance test the day
A2 lands. The companion behavior test (test_morph_cube_warns_or_animates)
guarantees the interim loud-warning path.
"""
import json
import os
import struct

import pytest
from pxr import Usd, UsdGeom, UsdSkel

from conftest import fetch_fixture, convert

EPSILON = 1e-4


# ---- minimal GLB reader (no deps beyond stdlib) -------------------------------

def parse_glb(path):
    with open(path, "rb") as fh:
        magic, _version, length = struct.unpack("<4sII", fh.read(12))
        assert magic == b"glTF", "not a GLB"
        chunks = {}
        while fh.tell() < length:
            clen, ctype = struct.unpack("<I4s", fh.read(8))
            chunks[ctype.strip(b"\x00")] = fh.read(clen)
    return json.loads(chunks[b"JSON"]), chunks[b"BIN"]


def read_accessor(gltf, bin_chunk, index):
    acc = gltf["accessors"][index]
    assert "sparse" not in acc, "sparse accessors not handled by this harness"
    view = gltf["bufferViews"][acc["bufferView"]]
    offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    fmt = {5126: "f", 5123: "H", 5125: "I", 5120: "b", 5121: "B", 5122: "h"}[acc["componentType"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    total = acc["count"] * ncomp
    return struct.unpack_from("<%d%s" % (total, fmt), bin_chunk, offset), acc["count"], ncomp


def gltf_morph_ground_truth(glb_path):
    """Returns (base_points, target_offsets[], times[], weights_per_time[])."""
    gltf, bin_chunk = parse_glb(glb_path)

    mesh = next(m for m in gltf["meshes"]
                if any("targets" in p for p in m["primitives"]))
    prim = next(p for p in mesh["primitives"] if "targets" in p)

    base, count, _ = read_accessor(gltf, bin_chunk, prim["attributes"]["POSITION"])
    base_pts = [base[i * 3:i * 3 + 3] for i in range(count)]

    targets = []
    for target in prim["targets"]:
        data, tcount, _ = read_accessor(gltf, bin_chunk, target["POSITION"])
        assert tcount == count
        targets.append([data[i * 3:i * 3 + 3] for i in range(tcount)])

    anim = next(a for a in gltf.get("animations", [])
                if any(c["target"]["path"] == "weights" for c in a["channels"]))
    channel = next(c for c in anim["channels"] if c["target"]["path"] == "weights")
    sampler = anim["samplers"][channel["sampler"]]
    times, _, _ = read_accessor(gltf, bin_chunk, sampler["input"])
    flat_weights, _, _ = read_accessor(gltf, bin_chunk, sampler["output"])
    n = len(targets)
    weights = [flat_weights[i * n:(i + 1) * n] for i in range(len(times))]
    return base_pts, targets, list(times), weights


def interpolate_weights(times, weights, t):
    if t <= times[0]:
        return weights[0]
    if t >= times[-1]:
        return weights[-1]
    for i in range(len(times) - 1):
        if times[i] <= t <= times[i + 1]:
            span = times[i + 1] - times[i]
            frac = 0.0 if span == 0 else (t - times[i]) / span
            return [a + (b - a) * frac for a, b in zip(weights[i], weights[i + 1])]
    return weights[-1]


# ---- the acceptance test -------------------------------------------------------

@pytest.mark.parametrize("name", ["AnimatedMorphCube", "AnimatedMorphSphere"])
def test_morph_conversion_matches_gltf_math(name):
    glb = fetch_fixture(name)
    out, code, _ = convert(glb, name + "_semantics")
    assert code == 0

    stage = Usd.Stage.Open(out)
    blendshapes = [p for p in stage.Traverse() if p.GetTypeName() == "BlendShape"]
    if not blendshapes:
        pytest.skip("morph support (A2) not implemented yet — harness is ready; "
                    "the loud-warning path is asserted by test_morph_cube_warns_or_animates")

    # --- authored side: mesh base points, blendshape offsets, weight curve ---
    mesh_prim = next(p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh))
    authored_base = [tuple(v) for v in UsdGeom.Mesh(mesh_prim).GetPointsAttr().Get()]

    binding = UsdSkel.BindingAPI(mesh_prim)
    shape_order = list(binding.GetBlendShapesAttr().Get() or [])
    shape_targets = list(binding.GetBlendShapeTargetsRel().GetTargets())
    offsets_by_shape = {}
    for target_path in shape_targets:
        shape = UsdSkel.BlendShape(stage.GetPrimAtPath(target_path))
        offsets_by_shape[target_path.name] = [tuple(v) for v in shape.GetOffsetsAttr().Get()]

    anim_prim = next(p for p in stage.Traverse() if p.GetTypeName() == "SkelAnimation")
    anim = UsdSkel.Animation(anim_prim)
    weight_attr = anim.GetBlendShapeWeightsAttr()
    time_samples = weight_attr.GetTimeSamples()
    assert len(time_samples) > 1, "blendshapes authored but weights not animated"
    tcps = stage.GetTimeCodesPerSecond()

    # --- independent side: raw glTF math ---
    g_base, g_targets, g_times, g_weights = gltf_morph_ground_truth(glb)
    assert len(authored_base) == len(g_base), "vertex count mismatch"
    assert len(offsets_by_shape) == len(g_targets), "blendshape count mismatch"

    # --- compare deformed points at every authored keyframe ---
    anim_shape_names = list(anim.GetBlendShapesAttr().Get() or shape_order)
    for tc in time_samples:
        authored_w = list(weight_attr.Get(tc))
        expected_w = interpolate_weights(g_times, g_weights, tc / tcps)

        for vi in range(len(g_base)):
            expected = list(g_base[vi])
            for ti, tgt in enumerate(g_targets):
                for c in range(3):
                    expected[c] += expected_w[ti] * tgt[vi][c]

            actual = list(authored_base[vi])
            for si, shape_name in enumerate(anim_shape_names):
                offs = offsets_by_shape.get(shape_name)
                assert offs is not None, "animation references unknown shape %s" % shape_name
                for c in range(3):
                    actual[c] += authored_w[si] * offs[vi][c]

            for c in range(3):
                assert abs(actual[c] - expected[c]) < EPSILON, (
                    "vertex %d axis %d at time %s: authored %.6f != glTF %.6f"
                    % (vi, c, tc, actual[c], expected[c]))
