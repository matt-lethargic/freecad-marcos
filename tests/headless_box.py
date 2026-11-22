"""
Headless smoke test for voronoi_cutout.py.

Run from the repo root with FreeCAD's command-line binary, e.g. on macOS:

    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_box.py').read())"

Optional: set VORONOI_OUT to a directory to save the result documents.
"""

import os
import sys

import FreeCAD as App
import Part

if "__file__" in globals():
    HERE = os.path.dirname(os.path.abspath(__file__))
else:  # run via `freecadcmd -c "exec(open(...).read())"` from the repo root
    HERE = os.path.join(os.getcwd(), "tests")
REPO = os.path.abspath(os.path.join(HERE, ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
OUT_DIR = os.environ.get("VORONOI_OUT")

import voronoi_cutout  # noqa: E402


def report(name, feature, before):
    result = feature.Shape
    tool = getattr(feature, "AddSubShape", None) or getattr(feature, "Cutter", None)
    cells = len(tool.Solids)
    removed = before - result.Volume
    print(
        "%-12s cells=%3d valid=%s solids=%d volume %.1f -> %.1f (removed %.1f)"
        % (name, cells, result.isValid(), len(result.Solids), before, result.Volume, removed)
    )
    assert result.isValid(), "%s: result shape is invalid" % name
    assert len(result.Solids) == 1, "%s: expected one solid, got %d" % (name, len(result.Solids))
    assert removed > 0, "%s: nothing was removed" % name
    return removed


def save(doc, name):
    if OUT_DIR:
        path = os.path.join(OUT_DIR, name + ".FCStd")
        doc.saveAs(path)
        print("   saved", path)


def check_part(name, shape, face_name, params):
    """Plain Part::Feature: the cutout becomes a Part::FeaturePython wrapping it."""
    doc = App.newDocument(name)
    base = doc.addObject("Part::Feature", "Plate")
    base.Shape = shape
    doc.recompute()

    feature = voronoi_cutout.create(base, face_name, params, doc)
    assert feature.TypeId == "Part::FeaturePython", feature.TypeId
    assert feature.Base is base
    removed = report(name, feature, base.Shape.Volume)
    save(doc, name)
    return feature, removed


def face_named(shape, predicate):
    for i, f in enumerate(shape.Faces):
        if predicate(f):
            return "Face%d" % (i + 1)
    raise AssertionError("no face matched")


def check_body(name, params):
    """
    PartDesign Body: a 100x60x30 box hollowed to 2 mm walls. Cutting the
    bottom face must land inside the body as the new tip.
    """
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    outer = doc.addObject("PartDesign::AdditiveBox", "Outer")
    body.addObject(outer)
    outer.Length, outer.Width, outer.Height = 100, 60, 30
    inner = doc.addObject("PartDesign::SubtractiveBox", "Inner")
    body.addObject(inner)
    inner.Length, inner.Width, inner.Height = 96, 56, 26
    inner.Placement.Base = App.Vector(2, 2, 2)
    doc.recompute()
    before = body.Shape.Volume

    bottom = face_named(
        inner.Shape,
        lambda f: isinstance(f.Surface, Part.Plane)
        and abs(f.Surface.Axis.z) > 0.9 and abs(f.CenterOfMass.z) < 1e-6,
    )
    feature = voronoi_cutout.create(inner, bottom, params, doc)
    doc.recompute()

    assert feature.TypeId == "PartDesign::FeatureSubtractivePython", feature.TypeId
    assert body.Tip is feature, "cutout should be the body tip, tip is %s" % body.Tip.Name
    assert feature.BaseFeature is inner
    assert feature in body.Group, "cutout is not inside the body"
    assert body.Shape.isValid()
    removed = report(name, feature, before)
    assert abs(body.Shape.Volume - feature.Shape.Volume) < 1e-6, "body shape should follow the tip"
    save(doc, name)
    return body, feature, removed


# Flat plate, through the single wall.
check_part(
    "plate",
    Part.makeBox(120, 80, 4),
    "Face6",
    {"point_count": 40, "seed": 7, "web_thickness": 3, "edge_margin": 5,
     "corner_radius": 1, "relax_iterations": 2},
)

# Thicker block, blind pocket of fixed depth on a side face, no rounding.
_, pocket_removed = check_part(
    "pocket",
    Part.makeBox(60, 100, 30),
    "Face2",
    {"point_count": 15, "seed": 1, "web_thickness": 2, "edge_margin": 4,
     "corner_radius": 0, "depth_mode": "Depth", "depth": 5},
)
assert pocket_removed < 5.5 * 60 * 100, "pocket cut deeper than 5 mm"

# Plate with a hole: the outline inset must grow the hole too.
# (Face numbering changes after the boolean; the top face ends up as Face3.)
plate = Part.makeBox(100, 100, 3)
hole = Part.makeCylinder(15, 10, App.Vector(50, 50, -1))
check_part(
    "ring",
    plate.cut(hole),
    "Face3",
    {"point_count": 60, "seed": 3, "web_thickness": 2.5, "edge_margin": 4,
     "corner_radius": 0.8, "min_spacing": 8, "relax_iterations": 1},
)

# Hollow body, "through next": only the 2 mm floor goes, the roof stays.
body, feature, removed_next = check_body(
    "hollow_next",
    {"point_count": 30, "seed": 5, "web_thickness": 3, "edge_margin": 4,
     "corner_radius": 1, "depth_mode": "Through next"},
)
assert removed_next < 2.5 * 100 * 60, "through-next removed more than the floor"
assert body.Shape.isInside(App.Vector(50, 30, 29), 1e-6, False), "roof was cut through"
assert not body.Shape.isInside(App.Vector(50, 30, 1), 1e-6, False), "floor still solid at a cell centre"

# Same body, "through all": roof goes too, so more is removed.
body_all, _, removed_all = check_body(
    "hollow_all",
    {"point_count": 30, "seed": 5, "web_thickness": 3, "edge_margin": 4,
     "corner_radius": 1, "depth_mode": "Through all"},
)
assert removed_all > removed_next * 1.5, "through-all should remove roof as well as floor"
assert abs(removed_all - 2 * removed_next) < 0.25 * removed_next, "through-all should be about twice through-next"

# Editing a property and recomputing regenerates the pattern.
feature.Seed = 99
feature.Document.recompute()
assert feature.Shape.isValid() and abs(feature.Shape.Volume - body.Shape.Volume) < 1e-6
print("hollow_next  reseeded ok, volume %.1f" % feature.Shape.Volume)

# A saved document must reopen with a working proxy and recompute.
if OUT_DIR:
    path = os.path.join(OUT_DIR, "hollow_next.FCStd")
    App.closeDocument(feature.Document.Name)
    reopened = App.openDocument(path)
    again = reopened.getObject("VoronoiCutout")
    assert again.Proxy is not None and isinstance(again.Proxy, voronoi_cutout.VoronoiCutout), "proxy lost on reload"
    again.Seed = 123
    again.touch()
    reopened.recompute()
    assert again.Shape.isValid() and again.Shape.Volume > 0, "reloaded feature failed to recompute"
    print("hollow_next  reload + recompute ok, volume %.1f" % again.Shape.Volume)

print("all headless checks passed")
