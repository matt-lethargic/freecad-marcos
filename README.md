# FreeCAD macros

Personal FreeCAD macros, kept here so they are versioned and safe.

| File | What it does |
| --- | --- |
| [`VoronoiCutout.FCMacro`](VoronoiCutout.FCMacro) | Select a planar face on a solid, set a few parameters, and a Voronoi cell pattern is cut into it as a parametric feature. |
| [`voronoi_cutout.py`](voronoi_cutout.py) | The geometry and the feature class behind the macro. Must be installed next to it. |
| [`VoronoiCells.FCMacro`](VoronoiCells.FCMacro) | The original experiment: draws Voronoi cells on a 100 x 100 sheet as separate faces. Kept for reference. |

## Install

FreeCAD loads macros from its user macro folder. On macOS with FreeCAD 1.1 that is
`~/Library/Application Support/FreeCAD/v1-1/Macro` (check `Macro > Macros... > User macros location`
if yours differs). Symlink the macros **and** the `.py` module into it so edits here show up in
FreeCAD straight away:

```bash
ln -sf "$PWD"/*.FCMacro "$PWD"/voronoi_cutout.py "$HOME/Library/Application Support/FreeCAD/v1-1/Macro/"
```

The `.py` file has to be in the macro folder, not just the repo: FreeCAD imports it again when a
document containing a Voronoi cutout is reopened.

## Voronoi Cutout

1. Open or build a solid (PartDesign body, Part box, anything with a `Shape`).
2. Click one planar face in the 3D view.
3. Run `Macro > Macros... > VoronoiCutout`.
4. Fill in the dialog and press OK.

**Inside a PartDesign Body** the cut is added as a subtractive feature after the current tip, so it
sits in the body's tree like a Pocket would. Later features build on it, and patterns and mirrors
can reuse it.

**Outside a body** (a Part box, an imported STEP, ...) a `Voronoi cutout` Part feature is created
with the original nested under it. Deleting the cutout shows the original again.

Either way the feature is parametric. Every setting is a property in the `Voronoi` group of the
property editor, so you can change the seed, web thickness, or depth mode after the fact and
recompute. The whole run is one undo step, and the dialog remembers your last values.

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
- The face is remembered by name (`Face12`). If an earlier feature changes the face numbering, the
  cutout may need its `Face` property pointing at the right face again.
- Each cell is one boolean prism, so several hundred cells can take a while to recompute.

## Headless test

With FreeCAD installed, this exercises a Part plate, a blind pocket, a plate with a hole, and a
hollow PartDesign body in both through modes, then reopens a saved result and recomputes it:

```bash
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_box.py').read())"
```

Set `VORONOI_OUT=/some/dir` to save the resulting `.FCStd` files (also enables the reload check).
