#!/usr/bin/env python3
"""Report USD-level stats for a USDZ so we can compare native output vs the oracle."""
import sys
from pxr import Usd, UsdGeom, UsdSkel

def report(path):
    stage = Usd.Stage.Open(path)
    if stage is None:
        print("FAILED TO OPEN:", path)
        return
    print("=== %s ===" % path)
    print("startTimeCode:", stage.GetStartTimeCode())
    print("endTimeCode  :", stage.GetEndTimeCode())
    print("timeCodesPerSecond:", stage.GetTimeCodesPerSecond())

    prims = list(stage.Traverse())
    print("total prims:", len(prims))

    meshes = [p for p in prims if p.IsA(UsdGeom.Mesh)]
    skels = [p for p in prims if p.IsA(UsdSkel.Skeleton)]
    skelAnims = [p for p in prims if p.IsA(UsdSkel.Animation)]
    print("meshes:", len(meshes), "| skeletons:", len(skels), "| skelAnimations:", len(skelAnims))

    for m in meshes:
        pts = UsdGeom.Mesh(m).GetPointsAttr()
        val = pts.Get()
        print("  mesh %s: %d points" % (m.GetPath(), len(val) if val else 0))

    # Count attributes that actually carry animation (>1 time sample).
    animated = 0
    for p in prims:
        for attr in p.GetAttributes():
            if attr.GetNumTimeSamples() > 1:
                animated += 1
    print("attributes with time samples (>1):", animated)

if __name__ == "__main__":
    for arg in sys.argv[1:]:
        report(arg)
