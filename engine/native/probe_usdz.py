#!/usr/bin/env python3
"""Report whether a USDZ actually carries animation. Prints '1', '0', or '?'.

Uses real USD introspection (not a byte scan), so it correctly detects skeletal
(UsdSkel) animation stored in binary crate files, where the literal string
'timeSamples' does not appear.
"""
import sys

try:
    from pxr import Usd

    stage = Usd.Stage.Open(sys.argv[1])
    animated = False
    if stage is not None:
        # A non-empty time range is the strongest signal (start != end).
        if stage.GetEndTimeCode() > stage.GetStartTimeCode():
            animated = True
        else:
            # Fallback: any attribute with more than one authored time sample.
            for prim in stage.Traverse():
                for attr in prim.GetAttributes():
                    if attr.GetNumTimeSamples() > 1:
                        animated = True
                        break
                if animated:
                    break
    print("1" if animated else "0")
except Exception:
    print("?")
