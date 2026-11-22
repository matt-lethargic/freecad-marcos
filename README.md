# FreeCAD macros

Personal FreeCAD macros, kept here so they are versioned and safe.

| Macro | What it does |
| --- | --- |
| [`VoronoiCutout.FCMacro`](VoronoiCutout.FCMacro) | Select a planar face on a solid, set a few parameters, and a Voronoi cell pattern is cut into it. |
| [`VoronoiCells.FCMacro`](VoronoiCells.FCMacro) | The original experiment: draws Voronoi cells on a 100 x 100 sheet as separate faces. Kept for reference. |

## Install

FreeCAD loads macros from its user macro folder. On macOS with FreeCAD 1.1 that is
`~/Library/Application Support/FreeCAD/v1-1/Macro` (check `Macro > Macros... > User macros location`
if yours differs). Symlink the repo's macros into it so edits here show up in FreeCAD straight away:

```bash
ln -s "$PWD"/*.FCMacro "$HOME/Library/Application Support/FreeCAD/v1-1/Macro/"
```

## Voronoi Cutout

1. Open or build a solid (Part box, PartDesign body, anything with a `Shape`).
2. Click one planar face in the 3D view.
3. Run `Macro > Macros... > VoronoiCutout`.
4. Fill in the dialog and press OK.

The macro adds a hidden `VoronoiTool` feature (the prisms it subtracts) and a `Part::Cut`
called `<object> Voronoi`. The original object is hidden, not deleted, so you can delete the cut
to get it back. The whole thing is one undo step. Settings are remembered between runs.

### Parameters

| Parameter | Meaning |
| --- | --- |
| Cell count | Number of seed points scattered over the face. More points, smaller cells. |
| Random seed | Same seed and settings reproduce the same pattern. |
| Min point spacing | Reject seed points closer than this. Gives more even cells. 0 turns it off. |
| Relax passes | Lloyd relaxation passes. Each pass moves seeds to their cell centroids, so cells become more regular. 0 keeps the raw random layout. |
| Web thickness | Material left between neighbouring cells. |
| Edge margin | Solid border kept around the edge of the face, including around any holes in it. |
| Corner radius | Fillet radius on every cell corner. Cells too small to be rounded are dropped. |
| Cut depth | How far to cut in from the face. 0 cuts right through the solid. |

### Limits

- The face must be planar. Curved faces are rejected with a message.
- Objects inside an `App::Part` container with its own placement are cut in the container's local
  coordinates, which will look wrong if the container is moved.
- Each cell is one boolean prism, so several hundred cells can take a while to recompute.

## Headless test

With FreeCAD installed, this cuts a plate, a blind pocket on a block, and a plate with a hole,
and checks each result is a single valid solid:

```bash
/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -c "exec(open('tests/headless_box.py').read())"
```

Set `VORONOI_OUT=/some/dir` to also save the resulting `.FCStd` files.
