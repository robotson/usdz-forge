"""Semantic animation profiler for USDZ output.

Opens a .usdz and returns a structured profile of what animation it actually
carries. The whole point: catch "converted successfully but the model is
frozen" — that bug class passes exit-code and file-exists checks, and a
byte-scan for 'timeSamples' misses UsdSkel animation in binary crates.

(Do NOT name this file inspect.py — it would shadow the stdlib module that
pxr imports and break everything.)
"""
import zipfile

from pxr import Usd, UsdGeom, UsdSkel


def profile(path):
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise RuntimeError("failed to open stage: %s" % path)

    out = {
        "range": (stage.GetStartTimeCode(), stage.GetEndTimeCode()),
        "skel_anims": [],
        "xform_anim_ops": 0,
        "blendshapes": [],
        "skeletons": 0,
        "meshes": 0,
        "zip_files": [],
    }

    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            out["meshes"] += 1
        if prim.IsA(UsdSkel.Skeleton):
            out["skeletons"] += 1
        if prim.GetTypeName() == "SkelAnimation":
            anim = UsdSkel.Animation(prim)
            out["skel_anims"].append({
                "path": str(prim.GetPath()),
                "joints": len(anim.GetJointsAttr().Get() or []),
                "rot_samples": len(anim.GetRotationsAttr().GetTimeSamples()),
                "trans_samples": len(anim.GetTranslationsAttr().GetTimeSamples()),
                "scale_samples": len(anim.GetScalesAttr().GetTimeSamples()),
                "blend_weight_samples": len(
                    anim.GetBlendShapeWeightsAttr().GetTimeSamples()),
            })
        if prim.GetTypeName() == "BlendShape":
            out["blendshapes"].append(str(prim.GetPath()))
        if prim.IsA(UsdGeom.Xformable):
            for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
                if len(op.GetTimeSamples()) > 1:
                    out["xform_anim_ops"] += 1

    with zipfile.ZipFile(str(path)) as z:
        out["zip_files"] = z.namelist()

    return out


def is_animated(p):
    """Any semantic animation at all in a profile."""
    if p["range"][1] > p["range"][0]:
        return True
    if p["xform_anim_ops"] > 0:
        return True
    return any(
        a["rot_samples"] > 1 or a["trans_samples"] > 1
        or a["scale_samples"] > 1 or a["blend_weight_samples"] > 1
        for a in p["skel_anims"]
    )
