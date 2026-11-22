"""
GUI smoke test for voronoi_cutout.py. Opens a real FreeCAD window, builds a
hollow body, cuts it, checks visibility and the double-click edit path, saves
screenshots, writes gui_check.txt next to this file, and closes FreeCAD.

Run from the repo root on macOS:

    /Applications/FreeCAD.app/Contents/MacOS/FreeCAD tests/gui_check.py

Output: tests/gui_check.txt (last line is OK or FAIL) and tests/gui_check_*.png.
"""

import os
import sys
import traceback

import FreeCAD as App
import FreeCADGui as Gui

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
lines = []

try:
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    import voronoi_cutout

    doc = App.newDocument("GuiCheck")
    body = doc.addObject("PartDesign::Body", "Body")
    outer = doc.addObject("PartDesign::AdditiveBox", "Outer")
    body.addObject(outer)
    outer.Length, outer.Width, outer.Height = 100, 60, 30
    inner = doc.addObject("PartDesign::SubtractiveBox", "Inner")
    body.addObject(inner)
    inner.Length, inner.Width, inner.Height = 96, 56, 26
    inner.Placement.Base = App.Vector(2, 2, 2)
    doc.recompute()
    inner.ViewObject.Visibility = True
    outer.ViewObject.Visibility = False

    bottom = None
    for i, f in enumerate(inner.Shape.Faces):
        if abs(f.CenterOfMass.z) < 1e-6 and abs(f.Surface.Axis.z) > 0.9:
            bottom = "Face%d" % (i + 1)
    feature = voronoi_cutout.create(inner, bottom, {"point_count": 20, "seed": 3})

    assert feature.ViewObject.Visibility, "new feature should be visible"
    assert not inner.ViewObject.Visibility, "previous tip should be hidden"
    assert body.Tip is feature
    assert isinstance(feature.ViewObject.Proxy, voronoi_cutout.ViewProviderVoronoiCutout)
    lines.append("body: feature visible, previous tip hidden, tip=%s vol=%.1f"
                 % (body.Tip.Name, feature.Shape.Volume))

    # Edit path without a modal dialog: stand in for the dialog.
    voronoi_cutout.ask_params = lambda current, title="": dict(current, seed=77)
    assert feature.ViewObject.Proxy.doubleClicked(feature.ViewObject)
    assert feature.Seed == 77 and feature.Shape.isValid()
    lines.append("double-click edit: seed now %d, shape valid" % feature.Seed)

    Gui.updateGui()
    Gui.ActiveDocument.ActiveView.viewBottom()
    Gui.SendMsgToActiveView("ViewFit")
    Gui.updateGui()
    Gui.ActiveDocument.ActiveView.saveImage(os.path.join(HERE, "gui_check_body.png"), 900, 600, "White")

    # Part workbench path: original nested under the cutout and hidden.
    import Part
    plate = doc.addObject("Part::Feature", "Plate")
    plate.Shape = Part.makeBox(50, 50, 3, App.Vector(0, 100, 0))
    doc.recompute()
    pf = voronoi_cutout.create(plate, "Face6", {"point_count": 10})
    assert pf.ViewObject.Visibility and not plate.ViewObject.Visibility
    assert [c.Name for c in pf.ViewObject.Proxy.claimChildren()] == ["Plate"]
    lines.append("part: feature visible, plate hidden and claimed as child")
    lines.append("OK")
except Exception:
    lines.append("FAIL\n" + traceback.format_exc())

with open(os.path.join(HERE, "gui_check.txt"), "w") as fh:
    fh.write("\n".join(lines) + "\n")

from PySide import QtCore  # noqa: E402
QtCore.QTimer.singleShot(800, lambda: Gui.getMainWindow().close())
