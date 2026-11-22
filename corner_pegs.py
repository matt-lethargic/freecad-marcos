# -*- coding: utf-8 -*-
"""
corner_pegs
===========

Geometry and the parametric feature behind CornerPegs.FCMacro.

Select the open end face(s) of a rectangular tube (a ring-shaped planar face
with a rectangular hole in it). The feature adds a quarter-round boss in each
inside corner, running a short way into the tube, and drills a peg hole into
each boss facing out of the end. Two tubes then join end to end with four
pegs, which make_peg() can also generate.

Installed as an addon (the repo linked into FreeCAD's user Mod folder) so the
feature restores when a document is reopened. FreeCAD 1.1 refuses feature
modules from the Macro folder.

    create(obj, "Face18", params)             # one end
    create(obj, ["Face1", "Face18"], params)  # both ends, one feature
    make_peg(doc, params)                     # a matching peg as a Part feature
"""

import FreeCAD as App
import Part

EPSILON = 1e-9
LIFT = 0.5  # holes start this far outside the end face so the boolean is clean

DEFAULTS = {
    "hole_diameter": 3.2,   # peg hole (mm); a 3 mm printed peg fits with clearance
    "hole_depth": 10.0,     # how far the hole goes into the boss (mm)
    "hole_inset": 3.0,      # hole centre distance from each inside wall (mm)
    "boss_radius": 8.0,     # quarter-round boss radius measured from the inside corner (mm)
    "boss_length": 12.0,    # how far the boss runs into the tube (mm)
    "peg_clearance": 0.2,   # peg diameter = hole diameter - clearance (mm)
}

PROPERTIES = [
    ("hole_diameter", "HoleDiameter", "App::PropertyLength",
     "Diameter of the peg hole"),
    ("hole_depth", "HoleDepth", "App::PropertyLength",
     "Depth of the peg hole measured from the end face"),
    ("hole_inset", "HoleInset", "App::PropertyLength",
     "Distance from each inside wall to the hole centre"),
    ("boss_radius", "BossRadius", "App::PropertyLength",
     "Radius of the quarter-round boss, from the inside corner"),
    ("boss_length", "BossLength", "App::PropertyLength",
     "How far the boss runs into the tube from the end face"),
    ("peg_clearance", "PegClearance", "App::PropertyLength",
     "Peg diameter is the hole diameter minus this"),
]


# ==================================
# GEOMETRY
# ==================================

def planar_surface(face):
    surface = face.Surface
    if not isinstance(surface, Part.Plane):
        raise ValueError("The selected face is not planar (%s)." % type(surface).__name__)
    return surface


def outward_normal(face, solid):
    """Unit normal of `face` pointing out of `solid`."""
    surface = planar_surface(face)
    centre = face.CenterOfMass
    u, v = surface.parameter(centre)
    normal = face.normalAt(u, v)
    normal.normalize()
    # Ring faces have their centre of mass in the hole, so probe a vertex instead.
    probe = face.Vertexes[0].Point if face.Vertexes else centre
    inside_pt = probe - normal * 0.05
    if solid.isInside(inside_pt, 1e-6, False):
        return normal
    if solid.isInside(probe + normal * 0.05, 1e-6, False):
        return normal * -1.0
    return normal


def inner_wire(face):
    outer = face.OuterWire
    inner = [w for w in face.Wires if not w.isSame(outer)]
    if len(inner) != 1:
        raise ValueError(
            "The selected face must be the end of a tube: one outer edge and exactly one "
            "inner opening (found %d)." % len(inner)
        )
    return inner[0]


def frame(face):
    """Orthonormal (u, v) axes lying in the face plane."""
    surface = planar_surface(face)
    u = App.Vector(surface.value(1, 0) - surface.value(0, 0))
    u.normalize()
    v = surface.Axis.cross(u)
    v.normalize()
    return u, v


def inner_rectangle(face):
    """
    The theoretical inside corners of the opening (chamfers and fillets are
    ignored by using the opening's bounding box in the face plane), the face
    centre, and the frame axes.
    """
    u, v = frame(face)
    wire = inner_wire(face)
    origin = face.Vertexes[0].Point
    us = []
    vs = []
    for vertex in wire.Vertexes:
        d = vertex.Point - origin
        us.append(d.dot(u))
        vs.append(d.dot(v))
    umin, umax, vmin, vmax = min(us), max(us), min(vs), max(vs)
    centre_u = (umin + umax) / 2.0
    centre_v = (vmin + vmax) / 2.0
    corners = []
    for cu in (umin, umax):
        for cv in (vmin, vmax):
            point = origin + u * cu + v * cv
            # Unit steps that lead from this corner towards the opening's middle.
            into_u = u if cu < centre_u else u * -1.0
            into_v = v if cv < centre_v else v * -1.0
            corners.append((point, into_u, into_v))
    opening = Part.Face(Part.makePolygon([
        origin + u * umin + v * vmin,
        origin + u * umax + v * vmin,
        origin + u * umax + v * vmax,
        origin + u * umin + v * vmax,
        origin + u * umin + v * vmin,
    ]))
    return corners, opening


def validate(params):
    """Raise ValueError if the sizes can't make a sound boss and hole."""
    full = dict(DEFAULTS)
    full.update(params or {})
    radius = float(full["boss_radius"])
    length = float(full["boss_length"])
    diameter = float(full["hole_diameter"])
    depth = float(full["hole_depth"])
    inset = float(full["hole_inset"])

    if radius <= 0 or length <= 0 or diameter <= 0 or depth <= 0:
        raise ValueError("Boss radius, boss length, hole diameter and hole depth must all be positive.")
    if depth > length:
        raise ValueError("Hole depth (%.1f) cannot exceed boss length (%.1f)." % (depth, length))
    if inset * 2 ** 0.5 + diameter / 2.0 > radius:
        raise ValueError(
            "Boss radius %.1f is too small: the hole (inset %.1f, diameter %.1f) would break "
            "out of it. Use a radius of at least %.1f." % (
                radius, inset, diameter, inset * 2 ** 0.5 + diameter / 2.0 + 1.0)
        )
    if float(full["peg_clearance"]) >= diameter:
        raise ValueError("Peg clearance leaves no peg.")
    return full


def build_corner_features(face, solid, params):
    """Returns (bosses, holes): lists of solids for one end face."""
    full = validate(params)
    radius = float(full["boss_radius"])
    length = float(full["boss_length"])
    diameter = float(full["hole_diameter"])
    depth = float(full["hole_depth"])
    inset = float(full["hole_inset"])

    normal = outward_normal(face, solid)
    inward = normal * -1.0
    corners, opening = inner_rectangle(face)

    bosses = []
    holes = []
    for point, into_u, into_v in corners:
        disc = Part.Face(Part.Wire(Part.makeCircle(radius, point, normal)))
        quarter = disc.common(opening)
        if quarter.Area <= EPSILON:
            raise ValueError("Could not fit a boss in a corner of the opening.")
        bosses.append(quarter.extrude(inward * length))

        hole_centre = point + into_u * inset + into_v * inset
        start = hole_centre + normal * LIFT
        holes.append(Part.makeCylinder(diameter / 2.0, depth + LIFT, start, inward))

    return bosses, holes


def apply(solid, faces, params):
    """Fuse bosses onto `solid` and drill the holes, for every face given."""
    all_bosses = []
    all_holes = []
    for face in faces:
        bosses, holes = build_corner_features(face, solid, params)
        all_bosses.extend(bosses)
        all_holes.extend(holes)

    result = solid.fuse(all_bosses)
    result = result.removeSplitter()
    result = result.cut(Part.makeCompound(all_holes))
    return result, all_bosses, all_holes


def peg_shape(params):
    full = dict(DEFAULTS)
    full.update(params or {})
    diameter = float(full["hole_diameter"]) - float(full["peg_clearance"])
    length = 2.0 * float(full["hole_depth"]) - 1.0  # leave a hair of slack at the join
    if diameter <= 0:
        raise ValueError("Peg clearance leaves no peg.")
    peg = Part.makeCylinder(diameter / 2.0, length)
    chamfer = min(0.5, diameter / 4.0)
    try:
        end_edges = [e for e in peg.Edges if isinstance(e.Curve, Part.Circle)]
        peg = peg.makeChamfer(chamfer, end_edges)
    except Exception:
        pass  # a square-ended peg still works
    return peg


# ==================================
# PARAMETRIC FEATURE
# ==================================

class CornerPegs:
    def __init__(self, obj, params=None):
        obj.Proxy = self
        obj.addProperty("App::PropertyLinkSubList", "Faces", "CornerPegs",
                        "Open end faces of the tube that get corner bosses and peg holes")
        for key, name, ptype, doc in PROPERTIES:
            obj.addProperty(ptype, name, "CornerPegs", doc)
        self.set_params(obj, params)

    @staticmethod
    def set_params(obj, params):
        full = dict(DEFAULTS)
        full.update(params or {})
        for key, name, ptype, doc in PROPERTIES:
            setattr(obj, name, full[key])

    @staticmethod
    def get_params(obj):
        return {key: float(getattr(obj, name)) for key, name, ptype, doc in PROPERTIES}

    @staticmethod
    def base_shape(obj):
        base = getattr(obj, "BaseFeature", None) or getattr(obj, "Base", None)
        if base is None or base.Shape.isNull():
            raise ValueError("Corner pegs feature has no base shape.")
        return base.Shape

    def execute(self, obj):
        solid = self.base_shape(obj)
        faces = []
        for link, subs in obj.Faces:
            for sub in subs:
                face = link.Shape.getElement(sub)
                if not isinstance(face, Part.Face):
                    raise ValueError("%s is not a face." % sub)
                faces.append(face)
        if not faces:
            raise ValueError("Corner pegs feature has no faces set.")

        result, bosses, holes = apply(solid, faces, self.get_params(obj))
        obj.Shape = result

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderCornerPegs:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def claimChildren(self):
        base = getattr(self.Object, "Base", None)
        return [base] if base is not None else []

    def doubleClicked(self, vobj):
        edit(vobj.Object)
        return True

    def setEdit(self, vobj, mode=0):
        if mode != 0:
            return None
        edit(vobj.Object)
        return False

    def unsetEdit(self, vobj, mode=0):
        return None

    def onDelete(self, vobj, subelements):
        previous = getattr(vobj.Object, "BaseFeature", None) or getattr(vobj.Object, "Base", None)
        if previous is not None and hasattr(previous, "ViewObject"):
            previous.ViewObject.Visibility = True
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


# ==================================
# GUI
# ==================================

def ask_params(current, title="Corner Pegs"):
    """Modal dialog; returns (params, make_peg_too) or None."""
    import FreeCADGui as Gui
    from PySide import QtWidgets

    dialog = QtWidgets.QDialog(Gui.getMainWindow())
    dialog.setWindowTitle(title)
    form = QtWidgets.QFormLayout(dialog)
    widgets = {}

    def add(key, label, low, high, step, tip):
        w = QtWidgets.QDoubleSpinBox()
        w.setDecimals(2)
        w.setSuffix(" mm")
        w.setRange(low, high)
        w.setSingleStep(step)
        w.setValue(float(current[key]))
        w.setToolTip(tip)
        form.addRow(label, w)
        widgets[key] = w

    add("hole_diameter", "Hole diameter", 0.5, 50, 0.1,
        "Peg hole diameter. The peg is this minus the clearance.")
    add("hole_depth", "Hole depth", 1, 200, 1,
        "How deep the hole goes in from the end face. Must not exceed the boss length.")
    add("hole_inset", "Hole inset", 0.5, 50, 0.5,
        "Distance from each inside wall to the hole centre.")
    add("boss_radius", "Boss radius", 1, 100, 0.5,
        "Quarter-round boss radius from the inside corner. Must cover the hole with some wall.")
    add("boss_length", "Boss length", 1, 500, 1,
        "How far the boss runs into the tube.")
    add("peg_clearance", "Peg clearance", 0, 2, 0.05,
        "Peg diameter is hole diameter minus this.")

    make_peg_box = QtWidgets.QCheckBox("Also create a matching peg part")
    make_peg_box.setChecked(bool(current.get("make_peg", True)))
    form.addRow(make_peg_box)

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)

    exec_fn = getattr(dialog, "exec", None) or dialog.exec_
    if exec_fn() != QtWidgets.QDialog.Accepted:
        return None
    params = {key: w.value() for key, w in widgets.items()}
    return params, make_peg_box.isChecked()


def edit(obj):
    current = CornerPegs.get_params(obj)
    current["make_peg"] = False
    answer = ask_params(current, "Edit corner pegs")
    if answer is None:
        return False
    params, make_peg_too = answer
    doc = obj.Document
    doc.openTransaction("Edit corner pegs")
    CornerPegs.set_params(obj, params)
    doc.recompute()
    if make_peg_too:
        make_peg(doc, params)
    doc.commitTransaction()
    return True


# ==================================
# DOCUMENT
# ==================================

def find_body(obj):
    if obj.TypeId == "PartDesign::Body":
        return obj
    parent = obj.getParentGeoFeatureGroup()
    if parent is not None and parent.TypeId == "PartDesign::Body":
        return parent
    return None


def create(obj, face_names, params=None, doc=None):
    """
    Add a CornerPegs feature to `obj` for the end faces `face_names` (a name
    or a list). Inside a PartDesign Body it becomes the tip; elsewhere it is
    a Part::FeaturePython with `obj` as Base. Returns the feature.
    """
    doc = doc or obj.Document
    body = find_body(obj)
    if isinstance(face_names, str):
        face_names = [face_names]
    face_names = [name.split(".")[-1] for name in face_names]
    if not face_names:
        raise ValueError("No faces given.")
    if body is not None and obj is body:
        obj = body.Tip

    # Check everything up front: errors raised during recompute are only
    # logged, which would leave a broken feature in the tree.
    validate(params)
    for name in face_names:
        face = obj.Shape.getElement(name)
        try:
            planar_surface(face)
            inner_wire(face)
        except ValueError as err:
            raise ValueError("%s: %s" % (name, err))

    if body is not None:
        feature = doc.addObject("PartDesign::FeaturePython", "CornerPegs")
        CornerPegs(feature, params)
        body.addObject(feature)
        previous = feature.BaseFeature
    else:
        feature = doc.addObject("Part::FeaturePython", "CornerPegs")
        CornerPegs(feature, params)
        feature.addProperty("App::PropertyLink", "Base", "CornerPegs", "Object the bosses are added to")
        feature.Base = obj
        previous = obj

    feature.Label = "Corner pegs"
    feature.Faces = [(obj, face_names)]
    doc.recompute()

    if App.GuiUp:
        ViewProviderCornerPegs(feature.ViewObject)
        if previous is not None and hasattr(previous, "ViewObject"):
            previous.ViewObject.Visibility = False
        feature.ViewObject.Visibility = True
    return feature


def make_peg(doc, params=None):
    """A peg to match the holes, as a plain Part feature placed beside the origin."""
    peg = doc.addObject("Part::Feature", "Peg")
    peg.Label = "Peg"
    peg.Shape = peg_shape(params)
    doc.recompute()
    return peg
