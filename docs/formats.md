# File formats

Each format has a JSON Schema in [schemas/](schemas/), generated from the code (`kei schema <name>` prints one).
A schema gives the shape. Kei's own checks (`kei check`, the gates) say whether the motion is right.

## shot.json, a keyed pass ([schema](schemas/shot.schema.json))

Each pass folder `out_<pass>/` holds one. It is the motion on Kei's rig v4:

    {"rig": "v4", "fps": 24, "frames": 48, "loop": true,
     "keys": [{"f": 0, "function": "contact", "root": [0, 0.95, 0], "footL": [-0.1, 0.08, 0.2]},
              {"f": 6, "function": "down", "tangent": "flat", "root": [0, 0.9, 0.1]}]}

- A key may leave out any channel. A channel it leaves out carries over from the key before, and the first key's
  missing channels take the default stand. A list channel may give its first numbers only.
- `tangent` is `auto` (clamped, the default) or `flat`. `"tangents": "free"` on the shot keeps the old unclamped curve.
- `objects` lists the things the character handles: a shape, a size, a rest point, a mass and `attach` frames
  (`hand_l`, `hand_r`, `hands`, or `floor` to let go). An object with a `path` moves on its own keys, and `grip` puts
  each hand on a point of it.

## plan.json, the plan's key poses ([schema](schemas/plan.schema.json))

`plan/plan.json` holds `keys`, each with an integer `f` and a `function` (the pose: contact, down, up, passing...),
and the delivery `camera` (`yaw_deg`, `pitch_deg`, `target_m`, `span_m` and the lens fields). A camera with
`keys` moves: each key changes some settings from its frame `f`, the camera eases between keys, and a key with
`"cut": true` starts a new setup. The plan gate also reads the X-sheet table in `PLAN.md`.

## PLAN.md and GATES.md

These are Markdown the agents write, read by the gates. `PLAN.md` carries the X-sheet table, the idea sentence and the
short look at the references. `GATES.md` carries the declarations of the flags a stage keeps on purpose, in
`Declared` sections. Kei writes the stage headers, hashes and counts itself in `KEI_RECORD.md`, so the agents keep no
bookkeeping lines.

## A lesson bundle ([schema of bundle.json](schemas/bundle.schema.json))

One folder of five files: `lesson.md`, `cases/fails/shot.json`, `cases/passes/shot.json`, `numbers.json` and
`bundle.json`, which holds the format (1), the Kei version and the sha256 of each other file. `kei share check`
refuses any other file, a changed file, a case Kei cannot play, or more than 2 MB.

## A reviewer's notes file ([schema](schemas/notes.schema.json))

Saved from a `kei pack` page as `<shot>_notes.json`: the shot, the pack id, the reviewer's name and the notes, each
with its text and, if given, its frames. `kei note <shot> --from-file` brings it in.
