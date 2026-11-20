# Engines and tools

`kei export <shot>` writes the approved (else the newest) pass on the shot's character as glTF (`.glb`); `--format
fbx` or `--format both` adds FBX 7.4. What both files hold:

- the skeleton, its rest pose as the bind pose. Bone names: the Unreal mannequin's, or with an imported character
  that kept its own skeleton, that model's own names (see below);
- the character's mesh, skinned to the skeleton;
- the objects of the shot (a crate, a ball): each its own mesh, not skinned, with its own colour and its own track;
- one animation per clip: a rotation per bone per frame, a translation where a bone's local translation moves, and a
  translation and rotation per object per frame.

## Options

| Option | What it does |
|---|---|
| `--clip <shot>[@<pass>]` | adds another shot as one more clip in the same file; repeat it for a whole set (idle, walk, run). The default pass is the approved one, else the newest. Every clip must be on the same character. |
| `--names source` (default) | an imported character that kept its own skeleton (`kei import` of a rigged model) exports with that model's bone names, so the file drops onto the skeleton it came from. Bones Kei has and the model had not keep Kei's names. A character on Kei's skeleton (the built-in ones, a model fitted to its mesh) keeps the mannequin names. |
| `--names kei` | the Unreal mannequin names always, for retargeting to the mannequin. |
| `--skeleton-only` | the skeleton and the animation only, no character mesh. Use it when the engine already has the character and you only bring in clips. Objects keep their tracks, as empty nodes. |

Each clip is named `<shot>_<pass>`. A character imported before Kei recorded the bone names reads them again from the
model file; when that file is gone, Kei says so and writes Kei's names.

## Axes and units

| File | Up | The model faces | Its right | Units |
|---|---|---|---|---|
| glTF | +y | +z | -x | metres |
| FBX | +y (UpAxis 1) | +z (FrontAxis 2) | -x | centimetres (UnitScaleFactor 1) |

The glTF also records this in `asset.extras.kei_axes`. Each tool converts these axes to its own at import; the settings
below are the ones that keep the size and the facing.

## Per tool

### Blender

Kei also animates in Blender itself (`kei run --app blender`; see the README's Blender section): it keys the key
poses in a background Blender and checks what Blender plays.

To take a file into your own Blender scene instead, use the glTF. File, Import, glTF 2.0, with the defaults: **+Y Up**
on (Blender turns it into its own +Z up) and no extra scale (both are metres). The character faces Blender's -Y, toward the front view. Each clip is an action on the
armature; the objects are separate meshes with their own actions, and an object moves only in the clips it is in. In
the FBX importer, keep **Apply Unit** on and the scale at 1.0, so the centimetres come in at the right size; its
**Animation Offset** of 1 starts Kei's frame 0 on Blender's frame 1 (the glTF starts on frame 0).

Checked in Blender 5.2 (20 November 2026): both files import at 1.71 m standing on the floor, with both clips of a
two-clip file and the crate of the carry clip on its path.

### Godot 4

Put the `.glb` in the project. Godot is +Y up and metres, like glTF, so no setting changes. The scene gets a
Skeleton3D, the meshes, and an AnimationPlayer with one animation per clip (the clip's name); the objects move under
the same AnimationPlayer.

### Unity

Use the FBX (Unity reads no glTF without a package). In the model's import settings: **Scale Factor** 1 with **Convert
Units** on, so centimetres become metres; on the Rig tab, **Humanoid** maps the mannequin names on its own (with
`--names kei`), **Generic** keeps any names. Each clip comes in as an animation take named after it.

### Unreal Engine

Live, through Claireon, Kei keys your Control Rig and bakes animation assets itself (`kei export --shot <shot> --pass
<pass> --to unreal`). From a file: import the FBX with the defaults, which convert +Y up to Unreal's +Z up and read
centimetres as they are. With `--names kei`, the skeleton matches the UE mannequin's names, so the IK Retargeter maps it
directly. Each clip in the file comes in as its own animation.

| Tool | Path | Tested by Kei |
|---|---|---|
| Unreal Engine | live in the editor through Claireon (keys, read-back, bake); or import the FBX or glTF | live on 5.8 with Claireon 2.2.0; `kei unreal check` compares your setup to that |
| Maya | live in an open or a background Maya (`kei maya`) | live; see the README's Maya section |
| Blender | live in a background Blender (`kei blender`), or import the glTF (or the FBX) | live on 5.2: key poses exact, an approved walk keyed with the same flags as Kei's own rig; imports checked by hand |
| Godot | the `.glb` in the project | not tested |
| Unity | import the FBX | not tested |

"Not tested" means nobody has checked that import with Kei's files yet. If you do, an issue that says what worked and
which settings you used is very welcome.
