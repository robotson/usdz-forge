#!/usr/bin/env python3
"""Verify texture references in a USDZ actually resolve to packaged assets."""
import sys
from pxr import Usd, UsdShade, Ar

def check(path):
    stage = Usd.Stage.Open(path)
    print("=== %s ===" % path)
    resolver = Ar.GetResolver()
    found = False
    for prim in stage.Traverse():
        shader = UsdShade.Shader(prim)
        if not shader:
            continue
        idAttr = shader.GetIdAttr().Get()
        if idAttr != 'UsdUVTexture':
            continue
        fileInput = shader.GetInput('file')
        if not fileInput:
            continue
        val = fileInput.Get()  # Sdf.AssetPath
        if val is None:
            continue
        found = True
        authored = val.path
        resolved = val.resolvedPath
        print("  texture prim:", prim.GetPath())
        print("    authored path :", authored)
        print("    resolved path :", resolved if resolved else "<UNRESOLVED>")
        print("    RESOLVES      :", "YES" if resolved else "NO")
    if not found:
        print("  (no UsdUVTexture shaders found)")

if __name__ == "__main__":
    for p in sys.argv[1:]:
        check(p)
