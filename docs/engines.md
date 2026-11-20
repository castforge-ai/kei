# Engines and tools

`kei export <shot>` writes the approved (else the newest) pass on the shot's character as glTF (`.glb`); `--format
fbx` or `--format both` adds FBX 7.4. What both files hold:

- the skeleton with the Unreal mannequin's bone names and hierarchy, its rest pose as the bind pose;
- one mesh, every vertex bound to one bone;
- one animation: a rotation per bone per frame, and a translation where a bone's local translation moves.

## Axes and units

| File | Up | The model faces | Its right | Units |
|---|---|---|---|---|
| glTF | +y | +z | -x | metres |
| FBX | +y (UpAxis 1) | +z (FrontAxis 2) | -x | centimetres (UnitScaleFactor 1) |

The glTF also records this in `asset.extras.kei_axes`. Each tool converts these axes to its own at import.

## Per tool

| Tool | Path | Tested by Kei |
|---|---|---|
| Unreal Engine | live in the editor through Claireon (keys, read-back, bake); or import the FBX or glTF | live on 5.8 with Claireon 2.2.0; `kei unreal check` compares your setup to that |
| Maya | live in an open or a background Maya (`kei maya`) | live; see the README's Maya section |
| Blender | File, Import, glTF 2.0: Blender's importer turns glTF's +y up into its +z up | not tested; no Blender adapter yet |
| Godot | drop the `.glb` into the project: Godot is +y up and reads glTF natively | not tested |
| Unity | the FBX, or the glTF through a glTF package | not tested |

"Not tested" means nobody has checked that import with Kei's files yet. If you do, an issue that says what worked and
which settings you used is very welcome.

## What the export does not do yet

The export writes Kei's skeleton with mannequin names, one clip per file, and no objects the character handles. An
imported character exports on Kei's bones, not its own. Those are on the audit list as engine-ready export.
