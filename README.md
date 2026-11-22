# FreeCAD macros

Personal FreeCAD macros, kept here so they are versioned and safe.

| File | What it does |
| --- | --- |
| [`VoronoiCutout.FCMacro`](VoronoiCutout.FCMacro) | Select a planar face on a solid, set a few parameters, and a Voronoi cell pattern is cut into it as a parametric feature. |
| [`CornerPegs.FCMacro`](CornerPegs.FCMacro) | Select the open end faces of a rectangular tube and each inside corner gets a boss with a peg hole facing out, so tubes join end to end with pegs. |
| [`voronoi_cutout.py`](voronoi_cutout.py), [`corner_pegs.py`](corner_pegs.py) | The geometry and feature classes behind the macros. Installed as an addon, see below. |
| [`VoronoiCells.FCMacro`](VoronoiCells.FCMacro) | The original experiment: draws Voronoi cells on a 100 x 100 sheet as separate faces. Kept for reference. |

## Install

Two symlinks, so edits here show up in FreeCAD straight away. On macOS with FreeCAD 1.1 the user
folder is `~/Library/Application Support/FreeCAD/v1-1` (check `Macro > Macros... > User macros
location` if yours differs). Run these from the repo folder.

The macros go in the `Macro` folder:

```bash
ln -sf "$PWD"/*.FCMacro "$HOME/Library/Application Support/FreeCAD/v1-1/Macro/"
```

The repo itself goes in the `Mod` folder, so FreeCAD treats its `.py` modules as an addon:

```bash
mkdir -p "$HOME/Library/Application Support/FreeCAD/v1-1/Mod" && ln -sfn "$PWD" "$HOME/Library/Application Support/FreeCAD/v1-1/Mod/freecad-marcos"
```

The modules must come from `Mod`, not `Macro`. When a document containing one of these features
is reopened, FreeCAD 1.1 re-imports the feature's module and only allows modules from its own
tree or from installed addons. With the module only in `Macro` the document still opens and keeps
its last shape, but the feature can't be edited or recomputed.

If you installed an earlier version, remove the old `voronoi_cutout.py` link from `Macro` and the
`Mod/VoronoiCutout` folder, so there is exactly one copy. Restart FreeCAD after changing `Mod`.

## Voronoi Cutout

1. Open or build a solid (PartDesign body, Part box, anything with a `Shape`).
2. Click one planar face in the 3D view, or Ctrl-click several faces of the same object.
3. Run `Macro > Macros... > VoronoiCutout`.
4. Fill in the dialog and press OK.

With several faces selected you get one feature that cuts all of them with the same settings.
Each face gets its own pattern (the seed is offset by the face's position in the list), and the
faces are cut one after another so patterns meeting at a corner don't fight each other.

**Inside a PartDesign Body** the cut is added as a subtractive feature after the current tip, so it
sits in the body's tree like a Pocket would. Later features build on it, and patterns and mirrors
can reuse it.

**Outside a body** (a Part box, an imported STEP, ...) a `Voronoi cutout` Part feature is created
with the original nested under it. Deleting the cutout shows the original again.

Either way the feature is parametric. Double-click `Voronoi cutout` in the tree to reopen the
dialog with its current values, or change the properties in the `Voronoi` group of the property
editor and recompute. The whole run is one undo step, and the dialog remembers your last values.

### Parameters

| Dialog | Property | Meaning |
| --- | --- | --- |
| Cell count | `PointCount` | Number of seed points scattered over the face. More points, smaller cells. |
| Random seed | `Seed` | Same seed and settings reproduce the same pattern. |
| Min point spacing | `MinSpacing` | Reject seed points closer than this. Gives more even cells. 0 turns it off. |
| Relax passes | `RelaxPasses` | Lloyd relaxation passes. Each pass moves seeds to their cell centroids, so cells become more regular. 0 keeps the raw random layout. |
| Web thickness | `WebThickness` | Material left between neighbouring cells. |
| Edge margin | `EdgeMargin` | Solid border kept around the edge of the face, including around any holes in it. |
| Corner radius | `CornerRadius` | Fillet radius on every cell corner. Cells too small to be rounded are dropped. |
| Cut | `DepthMode` | `Through next` (default) stops once each cell has passed through the first wall, so an opposite wall is left alone. `Through all` cuts everything behind the face. `Depth` cuts the fixed depth below. |
| Depth | `Depth` | Only used when `DepthMode` is `Depth`. |

`Through next` probes the solid at each cell's centre, so a face over a stepped or ribbed interior
gets a different depth per cell.

### Limits

- The face must be planar. Curved faces are rejected with a message.
- Faces are remembered by name (`Face12`). If an earlier feature changes the face numbering, the
  cutout may need its `Faces` property pointing at the right faces again.
- All faces of one cutout must belong to the same object. Select faces on two objects and the
  macro asks you to pick again.
- Each cell is one boolean prism, so several hundred cells can take a while to recompute.

## Corner Pegs

For joining tubes like the cable tray end to end. The tray's 2 mm walls are too thin to drill a
peg hole into, so the feature adds material first: a quarter-round boss tucked into each inside
corner, running a short way into the tube, with the hole drilled into the boss facing out.

1. Ctrl-click the open end face at each end of the tube. These are the ring-shaped faces with the
   opening in the middle.
2. Run `Macro > Macros... > CornerPegs`.
3. Check the sizes and press OK.

Inside a PartDesign Body it is added after the current tip, so it can go after a Voronoi cutout.
Double-click `Corner pegs` in the tree to edit it. Ticking "Also create a matching peg part" drops
a separate `Peg` object into the document, sized to the holes and chamfered at both ends, ready to
export and print. You need four pegs per join.

| Dialog | Property | Default | Meaning |
| --- | --- | --- | --- |
| Hole diameter | `HoleDiameter` | 3.2 mm | Peg hole diameter. |
| Hole depth | `HoleDepth` | 10 mm | How far the hole goes in from the end face. The peg is twice this, less 1 mm. |
| Hole inset | `HoleInset` | 3 mm | Distance from each inside wall to the hole centre. |
| Boss radius | `BossRadius` | 8 mm | Quarter-round boss radius from the inside corner. Must cover the hole with wall to spare, and the macro says so if it doesn't. |
| Boss length | `BossLength` | 12 mm | How far the boss runs into the tube. Must be at least the hole depth. |
| Peg clearance | `PegClearance` | 0.2 mm | Peg diameter is the hole diameter minus this. Tune it for your printer. |

The bosses sit at the theoretical inside corner, so inside chamfers or fillets on the tube are
simply filled in. The selected faces must each have exactly one rectangular opening.

## Headless tests

With FreeCAD installed, these exercise a Part plate, a blind pocket, a plate with a hole, a
hollow PartDesign body in both through modes and with two faces at once, a reopen-and-recompute
round trip, and corner pegs on a PartDesign tube and a Part tube including size validation:

```bash
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_box.py').read())"
```

```bash
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_pegs.py').read())"
```

Set `VORONOI_OUT=/some/dir` to save the resulting `.FCStd` files (also enables the reload check).

## GUI test

This opens a real FreeCAD window for a few seconds, cuts a hollow body, checks that the new feature
is visible and the old tip hidden, exercises the double-click edit, saves a screenshot to
`tests/gui_check_body.png`, and writes `tests/gui_check.txt` ending in `OK` or `FAIL`:

```bash
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD tests/gui_check.py
```
