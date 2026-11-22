# -*- coding: utf-8 -*-
"""
voronoi_cutout
==============

Geometry and the parametric feature behind VoronoiCutout.FCMacro.

This file must live next to the macro in FreeCAD's user Macro folder so the
feature's Python proxy can be found again when a document is reopened.

Two ways to use it:

    create(obj, "Face6", params)   # adds a parametric feature to the document
    build_tool(face, solid, params)  # just the cutter shape, no document

If `obj` sits inside a PartDesign Body the feature is a
PartDesign::FeatureSubtractivePython inserted after the tip, so the result
stays inside the body's tree. Otherwise it is a Part::FeaturePython with the
original object as its Base.

Every parameter is a property on the feature, so it can be changed in the
property editor and recomputed.
"""

import math
import random

import FreeCAD as App
import Part

EPSILON = 1e-9
LIFT = 0.5        # start prisms this far above the face: no coplanar faces for the boolean
OVERSHOOT = 0.2   # cut this far past the exit when going "through next"

DEPTH_MODES = ["Through next", "Through all", "Depth"]

DEFAULTS = {
    "point_count": 40,
    "seed": 42,
    "min_spacing": 0.0,
    "relax_iterations": 2,
    "web_thickness": 3.0,
    "edge_margin": 5.0,
    "corner_radius": 1.0,
    "depth_mode": "Through next",
    "depth": 5.0,
}

# (param key, property name, property type, description)
PROPERTIES = [
    ("point_count", "PointCount", "App::PropertyInteger",
     "Number of seed points (cells) scattered over the face"),
    ("seed", "Seed", "App::PropertyInteger",
     "Random seed. Same seed and settings reproduce the same pattern"),
    ("min_spacing", "MinSpacing", "App::PropertyLength",
     "Reject seed points closer than this. 0 disables it"),
    ("relax_iterations", "RelaxPasses", "App::PropertyInteger",
     "Lloyd relaxation passes. More passes give more regular cells"),
    ("web_thickness", "WebThickness", "App::PropertyLength",
     "Material left between neighbouring cells"),
    ("edge_margin", "EdgeMargin", "App::PropertyLength",
     "Solid border kept around the face outline, holes included"),
    ("corner_radius", "CornerRadius", "App::PropertyLength",
     "Fillet radius on cell corners. Cells too small to round are dropped"),
    ("depth_mode", "DepthMode", "App::PropertyEnumeration",
     "Through next: stop after the first wall. Through all: cut everything. "
     "Depth: use the Depth value"),
    ("depth", "Depth", "App::PropertyLength",
     "Cut depth, only used when DepthMode is Depth"),
]


# ==================================
# 2D GEOMETRY
# ==================================

def clip_polygon(polygon, a, b, c):
    """Sutherland-Hodgman clip of polygon against half-plane a*x + b*y <= c."""
    if not polygon:
        return []

    def inside(p):
        return a * p[0] + b * p[1] <= c + EPSILON

    def intersection(p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        denominator = a * dx + b * dy
        if abs(denominator) < EPSILON:
            return p1
        t = (c - a * p1[0] - b * p1[1]) / denominator
        return (p1[0] + t * dx, p1[1] + t * dy)

    result = []
    previous = polygon[-1]
    previous_inside = inside(previous)

    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                result.append(intersection(previous, current))
            result.append(current)
        elif previous_inside:
            result.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside

    return result


def voronoi_cell(index, points, rect, retreat):
    """
    Voronoi cell of points[index], clipped to rect = (umin, umax, vmin, vmax).

    Every bisector is moved `retreat` towards the seed, which leaves a web of
    2 * retreat between neighbouring cells.
    """
    sx, sy = points[index]
    umin, umax, vmin, vmax = rect
    polygon = [(umin, vmin), (umax, vmin), (umax, vmax), (umin, vmax)]

    for j, (ox, oy) in enumerate(points):
        if j == index:
            continue

        # Perpendicular bisector: 2(ox-sx)x + 2(oy-sy)y <= ox²+oy²-sx²-sy²
        a = 2.0 * (ox - sx)
        b = 2.0 * (oy - sy)
        c = ox * ox + oy * oy - sx * sx - sy * sy

        normal_length = math.sqrt(a * a + b * b)
        if normal_length < EPSILON:
            continue  # coincident seed, ignore it
        c -= retreat * normal_length

        polygon = clip_polygon(polygon, a, b, c)
        if len(polygon) < 3:
            return []

    return polygon


def polygon_centroid(polygon):
    n = len(polygon)
    area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < EPSILON:
        return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)
    area *= 0.5
    return (cx / (6.0 * area), cy / (6.0 * area))


def generate_points(rect, count, seed, min_spacing, accept):
    """
    Scatter `count` points inside rect, keeping only those `accept(u, v)` says
    are inside the face, and at least `min_spacing` apart (dart throwing).
    """
    umin, umax, vmin, vmax = rect
    rng = random.Random(seed)
    points = []
    attempts = 0
    max_attempts = max(count * 200, 1000)
    spacing_sq = min_spacing * min_spacing

    while len(points) < count and attempts < max_attempts:
        attempts += 1
        u = rng.uniform(umin, umax)
        v = rng.uniform(vmin, vmax)
        if not accept(u, v):
            continue
        if spacing_sq > 0 and any(
            (u - p[0]) ** 2 + (v - p[1]) ** 2 < spacing_sq for p in points
        ):
            continue
        points.append((u, v))

    return points


def relax_points(points, rect, iterations):
    """Lloyd relaxation: move each seed to the centroid of its cell."""
    for _ in range(iterations):
        moved = []
        for i, p in enumerate(points):
            cell = voronoi_cell(i, points, rect, 0.0)
            moved.append(polygon_centroid(cell) if len(cell) >= 3 else p)
        points = moved
    return points


# ==================================
# 3D GEOMETRY
# ==================================

def planar_surface(face):
    surface = face.Surface
    if not isinstance(surface, Part.Plane):
        raise ValueError(
            "The selected face is not planar (%s)." % type(surface).__name__
        )
    return surface


def cut_direction(face, solid):
    """Unit vector pointing from the face into the solid."""
    surface = planar_surface(face)
    centre = face.CenterOfMass
    u, v = surface.parameter(centre)
    normal = face.normalAt(u, v)
    normal.normalize()
    probe = 0.05
    if solid.isInside(centre - normal * probe, 1e-6, False):
        return normal * -1.0
    if solid.isInside(centre + normal * probe, 1e-6, False):
        return normal
    # Centre of mass can sit off the face (L-shapes). Faces of a solid carry
    # an outward normal, so inward is the safe default.
    return normal * -1.0


def exit_distance(solid, start, direction, max_length):
    """
    Distance along `direction` from `start` to where a ray first leaves the
    solid. `start` must sit just outside the solid. None if nothing is hit.
    """
    line = Part.makeLine(start, start + direction * max_length)
    try:
        common = line.common(solid)
    except Exception:
        return None
    ts = sorted(set(
        round((v.Point - start).dot(direction), 6)
        for e in common.Edges for v in e.Vertexes
    ))
    # First t is the entry (where the ray meets the face); the next is the exit.
    ts = [t for t in ts if t > LIFT * 0.5]
    if len(ts) < 2:
        return None
    return ts[1]


def face_from_polygon(polygon, surface):
    points = []
    for u, v in polygon:
        p = surface.value(u, v)
        if not points or (p - points[-1]).Length > 1e-6:
            points.append(p)
    if len(points) > 1 and (points[0] - points[-1]).Length <= 1e-6:
        points.pop()
    if len(points) < 3:
        return None
    wire = Part.makePolygon(points + [points[0]])
    return Part.Face(wire)


def offset_faces(face, distance):
    """2D offset of a face; returns the resulting faces (may be none)."""
    if abs(distance) < EPSILON:
        return [face]
    try:
        result = face.makeOffset2D(distance, 0, False, False, False)
    except Exception:  # OCC raises several types; a failed offset just means "nothing left"
        return []
    if result.isNull():
        return []
    return [f for f in result.Faces if f.Area > EPSILON]


def round_corners(face, radius):
    """Inset then outset with arc joins: every corner becomes a fillet."""
    if radius <= 0:
        return [face]
    rounded = []
    for inner in offset_faces(face, -radius):
        rounded.extend(offset_faces(inner, radius))
    return rounded


def build_cells(face, params):
    """
    Planar faces lying on `face`, one per surviving cell, already clipped to
    the inset outline and corner rounded.
    """
    surface = planar_surface(face)
    rect = face.ParameterRange
    margin = float(params["edge_margin"])

    outline = offset_faces(face, -margin)
    if not outline:
        raise ValueError("Edge margin is too large: nothing of the face is left.")
    outline = Part.makeCompound(outline)

    def accept(u, v):
        return outline.isInside(surface.value(u, v), 1e-6, True)

    points = generate_points(
        rect,
        int(params["point_count"]),
        int(params["seed"]),
        float(params["min_spacing"]),
        accept,
    )
    if not points:
        raise ValueError("No seed points fitted on the face. Lower min spacing or edge margin.")

    points = relax_points(points, rect, int(params["relax_iterations"]))

    retreat = float(params["web_thickness"]) / 2.0
    radius = float(params["corner_radius"])
    cell_faces = []

    for i in range(len(points)):
        polygon = voronoi_cell(i, points, rect, retreat)
        if len(polygon) < 3:
            continue
        cell = face_from_polygon(polygon, surface)
        if cell is None:
            continue
        clipped = cell.common(outline)
        for piece in clipped.Faces:
            if piece.Area <= EPSILON:
                continue
            cell_faces.extend(round_corners(piece, radius))

    return cell_faces


def build_tool(face, solid, params):
    """Compound of prisms, one per cell, ready to subtract from `solid`."""
    full = dict(DEFAULTS)
    full.update(params or {})

    cell_faces = build_cells(face, full)
    if not cell_faces:
        raise ValueError("No cells survived. Try more points, a thinner web, or a smaller margin/radius.")

    direction = cut_direction(face, solid)
    mode = full["depth_mode"]
    through_all = solid.BoundBox.DiagonalLength + 1.0

    if mode == "Depth":
        fixed = float(full["depth"])
        if fixed <= 0:
            raise ValueError("Depth must be greater than zero.")
    elif mode == "Through all":
        fixed = through_all
    elif mode == "Through next":
        fixed = None
    else:
        raise ValueError("Unknown depth mode %r." % mode)

    prisms = []
    for cell in cell_faces:
        start_face = cell.translated(direction * -LIFT)
        depth = fixed
        if depth is None:
            hit = exit_distance(solid, start_face.CenterOfMass, direction, through_all)
            depth = (hit - LIFT + OVERSHOOT) if hit is not None else through_all
        prisms.append(start_face.extrude(direction * (depth + LIFT)))

    return Part.makeCompound(prisms)


# ==================================
# PARAMETRIC FEATURE
# ==================================

class VoronoiCutout:
    """Proxy for the Part/PartDesign python feature."""

    def __init__(self, obj, params=None):
        obj.Proxy = self
        obj.addProperty("App::PropertyLinkSub", "Face", "Voronoi",
                        "Planar face the pattern is cut through")
        for key, name, ptype, doc in PROPERTIES:
            obj.addProperty(ptype, name, "Voronoi", doc)
        obj.DepthMode = DEPTH_MODES
        self.set_params(obj, params)

    @staticmethod
    def set_params(obj, params):
        full = dict(DEFAULTS)
        full.update(params or {})
        for key, name, ptype, doc in PROPERTIES:
            setattr(obj, name, full[key])

    @staticmethod
    def get_params(obj):
        return {key: getattr(obj, name) for key, name, ptype, doc in PROPERTIES}

    @staticmethod
    def base_shape(obj):
        base = getattr(obj, "BaseFeature", None) or getattr(obj, "Base", None)
        if base is None or base.Shape.isNull():
            raise ValueError("Voronoi cutout has no base shape to cut.")
        return base.Shape

    def execute(self, obj):
        solid = self.base_shape(obj)
        link, subs = obj.Face
        if link is None or not subs:
            raise ValueError("Voronoi cutout has no face set.")
        face = link.Shape.getElement(subs[0])
        if not isinstance(face, Part.Face):
            raise ValueError("%s is not a face." % subs[0])

        params = self.get_params(obj)
        # PropertyLength values come back as Quantity; the geometry wants floats.
        for key in ("min_spacing", "web_thickness", "edge_margin", "corner_radius", "depth"):
            params[key] = float(params[key])

        tool = build_tool(face, solid, params)
        if hasattr(obj, "AddSubShape"):
            obj.AddSubShape = tool  # PartDesign: lets patterns and mirrors reuse the cutter
        else:
            obj.Cutter = tool
        obj.Shape = solid.cut(tool)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderVoronoiCutout:
    """
    View side of the feature. Double-click opens the parameter dialog. In the
    Part workbench the base object is nested under the cutout; in a body the
    Body handles the tree and we only restore the previous tip on delete.
    """

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
        return False  # dialog is modal, nothing stays in edit mode

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

def ask_params(current, title="Voronoi Cutout"):
    """Modal dialog pre-filled with `current`; returns new params or None."""
    import FreeCADGui as Gui
    from PySide import QtWidgets

    dialog = QtWidgets.QDialog(Gui.getMainWindow())
    dialog.setWindowTitle(title)
    form = QtWidgets.QFormLayout(dialog)
    widgets = {}

    def add(key, label, low, high, step, decimals=None, tip=""):
        if decimals is None:
            w = QtWidgets.QSpinBox()
        else:
            w = QtWidgets.QDoubleSpinBox()
            w.setDecimals(decimals)
            w.setSuffix(" mm")
        w.setRange(low, high)
        w.setSingleStep(step)
        w.setValue(current[key])
        w.setToolTip(tip)
        form.addRow(label, w)
        widgets[key] = w

    add("point_count", "Cell count", 1, 5000, 5,
        tip="How many seed points (cells) to scatter over the face.")
    add("seed", "Random seed", 0, 999999, 1,
        tip="Same seed and settings give the same pattern.")
    add("min_spacing", "Min point spacing", 0, 1000, 1, 2,
        tip="Reject seed points closer than this. 0 disables it. Gives more even cells.")
    add("relax_iterations", "Relax passes", 0, 20, 1,
        tip="Lloyd relaxation passes. More passes = more regular, honeycomb-like cells.")
    add("web_thickness", "Web thickness", 0, 100, 0.5, 2,
        tip="Material left between neighbouring cells.")
    add("edge_margin", "Edge margin", 0, 100, 0.5, 2,
        tip="Solid border kept around the edge of the face.")
    add("corner_radius", "Corner radius", 0, 100, 0.25, 2,
        tip="Fillet radius on every cell corner. Cells too small to round are dropped.")

    mode = QtWidgets.QComboBox()
    mode.addItems(DEPTH_MODES)
    if current["depth_mode"] in DEPTH_MODES:
        mode.setCurrentText(current["depth_mode"])
    mode.setToolTip("Through next: stop after the first wall. Through all: cut everything "
                    "behind the face. Depth: cut the fixed depth below.")
    form.addRow("Cut", mode)

    add("depth", "Depth", 0.01, 10000, 1, 2,
        tip="Only used when Cut is set to Depth.")
    widgets["depth"].setEnabled(mode.currentText() == "Depth")
    mode.currentTextChanged.connect(lambda text: widgets["depth"].setEnabled(text == "Depth"))

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
    params["depth_mode"] = mode.currentText()
    return params


def edit(obj):
    """Open the dialog for an existing feature, apply and recompute."""
    current = VoronoiCutout.get_params(obj)
    for key in ("min_spacing", "web_thickness", "edge_margin", "corner_radius", "depth"):
        current[key] = float(current[key])
    params = ask_params(current, "Edit Voronoi cutout")
    if params is None:
        return False
    doc = obj.Document
    doc.openTransaction("Edit Voronoi cutout")
    VoronoiCutout.set_params(obj, params)
    doc.recompute()
    doc.commitTransaction()
    return True


def find_body(obj):
    """The PartDesign Body that owns `obj`, or None."""
    if obj.TypeId == "PartDesign::Body":
        return obj
    parent = obj.getParentGeoFeatureGroup()
    if parent is not None and parent.TypeId == "PartDesign::Body":
        return parent
    return None


def create(obj, face_name, params=None, doc=None):
    """
    Add a Voronoi cutout feature cutting `obj` through its face `face_name`.

    Inside a PartDesign Body the feature becomes the new tip. Anywhere else a
    Part::FeaturePython is created with `obj` as its Base. Returns the feature.
    """
    doc = doc or obj.Document
    body = find_body(obj)

    if body is not None:
        if obj is body:
            obj = body.Tip
            face_name = face_name.split(".")[-1]
        feature = doc.addObject("PartDesign::FeatureSubtractivePython", "VoronoiCutout")
        VoronoiCutout(feature, params)
        body.addObject(feature)  # inserts after the tip and sets BaseFeature
        previous = feature.BaseFeature
    else:
        feature = doc.addObject("Part::FeaturePython", "VoronoiCutout")
        VoronoiCutout(feature, params)
        feature.addProperty("App::PropertyLink", "Base", "Voronoi", "Object being cut")
        feature.addProperty("Part::PropertyPartShape", "Cutter", "Voronoi",
                            "The prisms subtracted from Base")
        feature.Base = obj
        previous = obj

    feature.Label = "Voronoi cutout"
    feature.Face = (obj, [face_name])
    doc.recompute()

    if App.GuiUp:
        # Python-added features start hidden; mimic what the Pocket command does.
        ViewProviderVoronoiCutout(feature.ViewObject)
        if previous is not None and hasattr(previous, "ViewObject"):
            previous.ViewObject.Visibility = False
        feature.ViewObject.Visibility = True
    return feature
