"""Regression suite: assert on the semantic animation content of the output.

Guards the "converts successfully but the model is frozen" bug class. Each
fixture declares its expected animation profile; exit codes and file existence
are necessary but never sufficient.
"""
import os
import zipfile

import pytest

from anim_probe import profile, is_animated
from conftest import fetch_fixture, convert

MORPH_WARNING = "morph targets/blendshapes detected"


def run(name):
    glb = fetch_fixture(name)
    out, code, log = convert(glb, name)
    assert code == 0, "conversion failed:\n%s" % log
    assert os.path.exists(out), "no output file produced"
    return profile(out), log, out


# ---- rigid / node animation -------------------------------------------------

def test_box_animated_keeps_node_animation():
    p, _, _ = run("BoxAnimated")
    assert p["xform_anim_ops"] > 0, "node-transform animation was dropped"
    assert p["range"][1] > p["range"][0]


# ---- skinned / skeletal -----------------------------------------------------

def test_cesium_man_keeps_skeletal_animation():
    """The T-pose regression guard."""
    p, _, out = run("CesiumMan")
    assert len(p["skel_anims"]) == 1
    anim = p["skel_anims"][0]
    assert anim["joints"] >= 19
    assert anim["rot_samples"] > 1, "joint rotations lost -> T-pose"
    assert anim["trans_samples"] > 1, "joint translations lost -> T-pose"
    assert p["range"][1] > p["range"][0]
    # texture embedded in the package
    assert any(f.endswith(".jpg") or f.endswith(".png") for f in p["zip_files"]), \
        "expected an embedded texture in the usdz"


def test_brainstem_keeps_skeletal_animation():
    p, _, _ = run("BrainStem")
    assert len(p["skel_anims"]) >= 1
    assert any(a["rot_samples"] > 1 for a in p["skel_anims"])


# ---- morph / blendshape (documented-behavior test, never silent) ------------

def test_morph_cube_warns_or_animates():
    """Morph input must never produce a silently static file."""
    p, log, _ = run("AnimatedMorphCube")
    if is_animated(p) or p["blendshapes"]:
        # A2 implemented: blendshape data survived
        assert any(a["blend_weight_samples"] > 1 for a in p["skel_anims"]), \
            "blendshapes present but no weight animation"
    else:
        # A1 behavior: static output is only acceptable WITH a loud warning
        assert MORPH_WARNING in log, \
            "morph input produced a static file with NO warning (silent failure)"


def test_skinned_input_does_not_morph_warn():
    """The morph warning must not fire on clean skinned input."""
    _, log, _ = run("CesiumMan")
    assert MORPH_WARNING not in log


# ---- multi-clip: documented single-timeline behavior -------------------------

def test_fox_multi_clip_authors_all_clips():
    p, _, _ = run("Fox")
    # Finding (2026-07-08): the engine authors ALL THREE clips (Survey/Walk/Run)
    # as separate SkelAnimation prims — richer than "one timeline survives".
    # AR Quick Look still plays only the bound clip; that's a viewer limit.
    assert len(p["skel_anims"]) == 3, "expected all three Fox clips authored"
    assert all(a["joints"] == 20 for a in p["skel_anims"])
    assert is_animated(p)


# ---- static control ----------------------------------------------------------

def test_static_box_invents_no_animation():
    p, _, _ = run("Box")
    assert not is_animated(p), "spurious animation invented on a static model"


# ---- textured PBR ------------------------------------------------------------

def test_damaged_helmet_embeds_textures():
    p, _, _ = run("DamagedHelmet")
    images = [f for f in p["zip_files"] if f.endswith((".jpg", ".png"))]
    assert len(images) >= 1, "textures missing from the package"
    assert p["meshes"] >= 1


# ---- failure containment (batch mode relies on this) --------------------------

def test_corrupt_input_fails_cleanly():
    """A bad file must fail with a nonzero exit and no output — never hang or
    'succeed'. The app's batch mode catches this per file and continues."""
    import conftest
    os.makedirs(conftest.FIXTURES_DIR, exist_ok=True)
    bad = os.path.join(conftest.FIXTURES_DIR, "corrupt.glb")
    with open(bad, "wb") as fh:
        fh.write(b"this is definitely not a valid glb file")
    out, code, log = convert(bad, "corrupt")
    assert code != 0, "corrupt input reported success"
    assert not os.path.exists(out), "corrupt input still produced an output file"


# ---- package integrity (every fixture) ----------------------------------------

@pytest.mark.parametrize("name", [
    "BoxAnimated", "CesiumMan", "AnimatedMorphCube", "Fox", "Box", "DamagedHelmet",
])
def test_package_integrity(name):
    glb = fetch_fixture(name)
    out, code, _ = convert(glb, name + "_integrity")
    assert code == 0
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names, "empty usdz"
        assert names[0].endswith(".usdc"), \
            "first zip entry must be the .usdc (got %s)" % names[0]
        assert not any(n.startswith("/") or ".." in n for n in names), \
            "unsafe path inside usdz"
        assert z.testzip() is None, "corrupt zip member"
