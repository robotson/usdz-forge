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

MORPH_WARNING = "morph targets detected"


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


# ---- Tier 1b: skinned + morph composite (the real-character case) -------------

def test_robot_expressive_skin_and_morph_in_same_clip():
    """Skeleton AND blendshapes driven by one clip — the real-character
    scenario (body via bones, face via morphs) that no Khronos sample covers.
    The 'Dance' clip must carry joint rotations AND blendshape weights."""
    import conftest
    out, code, log = convert(
        os.path.join(conftest.VENDORED_DIR, "RobotExpressive.glb"), "RobotExpressive")
    assert code == 0
    p = profile(out)
    assert p["skeletons"] >= 1
    assert len(p["blendshapes"]) >= 1
    assert len(p["skel_anims"]) == 14, "all 14 clips should be authored"
    composite = [a for a in p["skel_anims"]
                 if a["rot_samples"] > 1 and a["blend_weight_samples"] > 1]
    assert composite, "no clip drives joints AND blendshape weights together"

    # Regression guard: rigid meshes bound with WORLD-space geomBindTransforms
    # double-applied the armature's scale=100 (robot rendered 100x too big ->
    # blank AR view). Bind transforms must be armature-relative: scale ~= 1.
    from pxr import Usd, UsdGeom, UsdSkel, Gf
    stage = Usd.Stage.Open(out)
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        gbt = UsdSkel.BindingAPI(prim).GetGeomBindTransformAttr().Get()
        if gbt is None:
            continue
        scale = Gf.Transform(gbt).GetScale()
        for component in scale:
            assert abs(component) < 10, \
                "geomBindTransform carries ancestor scale (%s on %s) - " \
                "world/skel space mismatch" % (scale, prim.GetPath())


def test_rpm_avatar_skeleton_and_morphs_coexist():
    """Ready Player Me avatar: full body skeleton + the 72-target ARKit facial
    morph set (268 BlendShape prims across 10 meshes). Authoring a large morph
    set must not drop the skeleton, and vice versa."""
    import conftest
    out, code, log = convert(
        os.path.join(conftest.VENDORED_DIR, "brunette-t.glb"), "brunette_t")
    assert code == 0
    p = profile(out)
    assert p["skeletons"] >= 1, "skeleton dropped"
    assert len(p["blendshapes"]) >= 72, "ARKit morph set incomplete"
    assert "morph targets detected" in log


# ---- expanded battery: rigs, robustness, draco, orientation -------------------

def test_recursive_skeletons_converts():
    """Regression: strided/interleaved accessors crashed on a Py2 relic
    (data = '' instead of b'' in Accessor). RecursiveSkeletons exercises it."""
    p, _, _ = run("RecursiveSkeletons")
    assert p["meshes"] == 84
    assert len(p["skel_anims"]) >= 1
    assert is_animated(p)


@pytest.mark.parametrize("name", ["RiggedFigure", "RiggedSimple"])
def test_minimal_rigs_keep_animation(name):
    p, _, _ = run(name)
    assert len(p["skel_anims"]) >= 1
    assert is_animated(p)


def test_interpolation_modes_convert():
    """STEP / LINEAR / CUBICSPLINE samplers all convert and animate."""
    p, _, _ = run("InterpolationTest")
    assert is_animated(p)


def test_sparse_morph_targets_warn_or_author():
    """MorphPrimitivesTest uses sparse morph accessors. Never silent: either
    blendshapes were authored, or the sparse-drop warning fired."""
    glb = fetch_fixture("MorphPrimitivesTest")
    out, code, log = convert(glb, "MorphPrimitivesTest")
    assert code == 0
    p = profile(out)
    assert p["blendshapes"] or "sparse" in log, \
        "sparse morphs neither authored nor warned about (silent loss)"


@pytest.mark.parametrize("name", ["Lantern", "MaterialsVariantsShoe", "DragonAttenuation"])
def test_realworld_materials_no_crash(name):
    """KHR material extensions / heavy PBR: fidelity loss is acceptable,
    crashing is not."""
    p, _, _ = run(name)
    assert p["meshes"] >= 1


def test_lantern_package_size():
    """Mobile web-AR delivery cares about size; flag runaway packages."""
    glb = fetch_fixture("Lantern")
    out, code, _ = convert(glb, "Lantern_size")
    assert code == 0
    size_mb = os.path.getsize(out) / 1e6
    assert size_mb < 20, "package unexpectedly huge (%.1f MB)" % size_mb


def test_draco_rejected_cleanly():
    """Draco geometry lives in the extension, not plain accessors — it must
    fail with actionable guidance, never a KeyError traceback."""
    vendored = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "vendored", "BoxAnimated_draco.glb")
    out, code, log = convert(vendored, "draco")
    assert code != 0, "Draco input reported success"
    assert not os.path.exists(out)
    assert "Draco" in log, "no actionable Draco message"
    assert "Traceback" not in log, "raw stack trace leaked to the user"


def test_output_up_axis_is_y():
    """Guard the original 'orientation was whacked in Preview' complaint:
    outputs must be Y-up (glTF convention, Quick Look expectation)."""
    from pxr import Usd, UsdGeom
    glb = fetch_fixture("CesiumMan")
    out, code, _ = convert(glb, "CesiumMan_axis")
    assert code == 0
    stage = Usd.Stage.Open(out)
    assert str(UsdGeom.GetStageUpAxis(stage)) == "Y"


# ---- ARKit compliance (B4): Apple's own validator must pass every fixture ----

@pytest.mark.parametrize("name", [
    "BoxAnimated", "CesiumMan", "AnimatedMorphCube", "Fox", "Box", "DamagedHelmet",
])
def test_arkit_checker_passes(name):
    import subprocess
    from conftest import ENGINE_PYTHON, REPO_ROOT
    glb = fetch_fixture(name)
    out, code, _ = convert(glb, name + "_arkit")
    assert code == 0
    checker = os.path.join(REPO_ROOT, "engine", "native", "realityConvertChecker.py")
    proc = subprocess.run(
        [ENGINE_PYTHON, checker, out],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, \
        "usdARKitChecker failed for %s:\n%s%s" % (name, proc.stdout, proc.stderr)


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
