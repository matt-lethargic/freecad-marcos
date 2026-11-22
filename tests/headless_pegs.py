"""
Headless smoke test for corner_pegs.py.

Run from the repo root:

    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_pegs.py').read())"

Set VORONOI_OUT to a directory to save the result documents.
"""

import math
import os
import sys

import FreeCAD as App
import Part

if "__file__" in globals():
    HERE = os.path.dirname(os.path.abspath(__file__))
else:
    HERE = os.path.join(os.getcwd(), "tests")
REPO = os.path.abspath(os.path.join(HERE, ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
OUT_DIR = os.environ.get("VORONOI_OUT")

import corner_pegs  # noqa: E402

PARAMS = {"hole_diameter": 3.2, "hole_depth": 10, "hole_inset": 3, "boss_radius": 8, "boss_length": 12}


def save(doc, name):
    if OUT_DIR:
        path = os.path.join(OUT_DIR, name + ".FCStd")
        doc.saveAs(path)
        print("   saved", path)


def end_faces(shape, axis):
    """Names of the two planar ring faces normal to `axis`."""
    names = []
    for i, f in enumerate(shape.Faces):
        if isinstance(f.Surface, Part.Plane) and abs(f.Surface.Axis.dot(axis)) > 0.99 and len(f.Wires) == 2:
            names.append("Face%d" % (i + 1))
    assert len(names) == 2, "expected two ring end faces, found %s" % names
    return names


def check_tube(name, length):
    """A 120x70 tube, 2 mm walls, open both ends, built as a PartDesign body."""
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    outer = doc.addObject("PartDesign::AdditiveBox", "Outer")
    body.addObject(outer)
    outer.Length, outer.Width, outer.Height = 120, 70, length
    inner = doc.addObject("PartDesign::SubtractiveBox", "Inner")
    body.addObject(inner)
    inner.Length, inner.Width, inner.Height = 116, 66, length + 2
    inner.Placement.Base = App.Vector(2, 2, -1)
    doc.recompute()
    before = body.Shape.Volume

    faces = end_faces(inner.Shape, App.Vector(0, 0, 1))
    feature = corner_pegs.create(inner, faces, PARAMS, doc)
    doc.recompute()
    shape = feature.Shape

    assert feature.TypeId == "PartDesign::FeaturePython"
    assert body.Tip is feature
    assert shape.isValid() and len(shape.Solids) == 1, "result should be one valid solid"

    # Expected volume: 8 quarter-round bosses less the overlap with the chamfer-free
    # corner, minus 8 holes. The bosses sit inside the opening so no overlap with walls.
    r, l, d, h = 8.0, 12.0, 3.2, 10.0
    boss_volume = 8 * (math.pi * r * r / 4.0) * l
    hole_volume = 8 * math.pi * (d / 2.0) ** 2 * h
    expected = before + boss_volume - hole_volume
    added = shape.Volume - before
    print("%-10s volume %.1f -> %.1f (added %.1f, expected +%.1f)" % (name, before, shape.Volume, added, expected - before))
    assert abs(shape.Volume - expected) < 0.01 * expected, "volume off: %.1f vs %.1f" % (shape.Volume, expected)

    # Each hole centre is 3 mm in from both inside walls (which are at 2 mm), 5 mm deep.
    for x in (5.0, 115.0):
        for y in (5.0, 65.0):
            for z in (5.0, length - 5.0):
                assert not shape.isInside(App.Vector(x, y, z), 1e-6, False), "no hole at %s" % ((x, y, z),)
            # Boss material next to the hole, and beyond the hole depth.
            assert shape.isInside(App.Vector(x + (2.5 if x < 60 else -2.5), y, 5.0), 1e-6, False), "boss missing beside hole"
            assert shape.isInside(App.Vector(x, y, 11.0), 1e-6, False), "boss should be solid past the hole bottom"
            assert not shape.isInside(App.Vector(x, y, 13.0), 1e-6, False), "boss should stop at 12 mm"

    # Hole count: cylindrical faces with the hole radius.
    hole_faces = [f for f in shape.Faces if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 1.6) < 1e-6]
    assert len(hole_faces) == 8, "expected 8 hole walls, got %d" % len(hole_faces)

    peg = corner_pegs.make_peg(doc, PARAMS)
    assert peg.Shape.isValid()
    bb = peg.Shape.BoundBox
    assert abs(bb.XLength - 3.0) < 1e-6 and abs(bb.ZLength - 19.0) < 1e-6, "peg should be 3 mm x 19 mm"
    print("%-10s peg %.2f x %.1f mm" % (name, bb.XLength, bb.ZLength))
    save(doc, name)
    return feature


check_tube("tube", 220)

# Parameter validation.
doc = App.newDocument("bad")
base = doc.addObject("Part::Feature", "Tube")
base.Shape = Part.makeBox(60, 40, 50).cut(Part.makeBox(56, 36, 52, App.Vector(2, 2, -1)))
doc.recompute()
try:
    corner_pegs.create(base, end_faces(base.Shape, App.Vector(0, 0, 1)), dict(PARAMS, boss_radius=4), doc)
    raise AssertionError("small boss radius should be rejected")
except ValueError as err:
    print("rejected:   ", err)
try:
    corner_pegs.create(base, "Face1", PARAMS, doc)  # a wall, not a ring
    raise AssertionError("a face without an opening should be rejected")
except ValueError as err:
    print("rejected:   ", err)

# Part workbench path on the same box tube, and editing a property.
feature = corner_pegs.create(base, end_faces(base.Shape, App.Vector(0, 0, 1)), PARAMS, doc)
assert feature.TypeId == "Part::FeaturePython" and feature.Base is base
assert feature.Shape.isValid() and len(feature.Shape.Solids) == 1
v1 = feature.Shape.Volume
feature.HoleDepth = 5
doc.recompute()
assert feature.Shape.Volume > v1, "shallower holes should leave more material"
print("part       edit ok, volume %.1f -> %.1f" % (v1, feature.Shape.Volume))

print("all corner peg checks passed")
