"""
Headless smoke test for VoronoiCutout.FCMacro.

Run with FreeCAD's command-line binary, e.g. on macOS:

    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd tests/headless_box.py

Optional: set VORONOI_OUT to a directory to save the result documents.
"""

import os
import runpy
import sys

import FreeCAD as App
import Part

if "__file__" in globals():
    HERE = os.path.dirname(os.path.abspath(__file__))
else:  # run via `freecadcmd -c "exec(open(...).read())"` from the repo root
    HERE = os.path.join(os.getcwd(), "tests")
MACRO = os.path.join(HERE, "..", "VoronoiCutout.FCMacro")
OUT_DIR = os.environ.get("VORONOI_OUT")

macro = runpy.run_path(MACRO)
run = macro["run"]


def check(name, shape_obj, face_name, params):
    doc = App.newDocument(name)
    base = doc.addObject("Part::Feature", "Plate")
    base.Shape = shape_obj
    doc.recompute()

    cut = run(base, face_name, params, doc)
    result = cut.Shape

    cells = len(cut.Tool.Shape.Solids)
    removed = base.Shape.Volume - result.Volume
    print(
        "%-12s cells=%3d valid=%s solids=%d volume %.1f -> %.1f (removed %.1f)"
        % (name, cells, result.isValid(), len(result.Solids),
           base.Shape.Volume, result.Volume, removed)
    )

    assert result.isValid(), "%s: result shape is invalid" % name
    assert len(result.Solids) == 1, "%s: expected one solid, got %d" % (name, len(result.Solids))
    assert cells > 0, "%s: no cells were cut" % name
    assert removed > 0, "%s: nothing was removed" % name

    if OUT_DIR:
        path = os.path.join(OUT_DIR, name + ".FCStd")
        doc.saveAs(path)
        print("   saved", path)
    return cut


# Flat plate, through-cut from the top face.
check(
    "plate",
    Part.makeBox(120, 80, 4),
    "Face6",
    {"point_count": 40, "seed": 7, "web_thickness": 3, "edge_margin": 5,
     "corner_radius": 1, "relax_iterations": 2},
)

# Thicker block, blind pocket on the side face, no rounding.
check(
    "pocket",
    Part.makeBox(60, 100, 30),
    "Face2",
    {"point_count": 15, "seed": 1, "web_thickness": 2, "edge_margin": 4,
     "corner_radius": 0, "depth": 5},
)

# Plate with a hole: the outline inset must grow the hole too.
# (Face numbering changes after the boolean; the top face ends up as Face3.)
plate = Part.makeBox(100, 100, 3)
hole = Part.makeCylinder(15, 10, App.Vector(50, 50, -1))
check(
    "ring",
    plate.cut(hole),
    "Face3",
    {"point_count": 60, "seed": 3, "web_thickness": 2.5, "edge_margin": 4,
     "corner_radius": 0.8, "min_spacing": 8, "relax_iterations": 1},
)

print("all headless checks passed")
