Block the shot: key poses only, stepped, matching the plan sheet. Key the shot on Kei's own rig: write the keys to
out_blocking/shot.json, then run `kei render <shot> blocking`. It writes a still per key (key_f0000.png...), a key
sheet (keys.png) and the stepped playback out_blocking/blocking.mp4 (blocking.gif when ffmpeg is missing). Look at
them. Write GATES.md with "## Blocking gate: pass" and the lines "- balance:", "- arcs:", "- timing:" and "- story:",
each saying what you saw. A gate you cannot pass honestly is not written as pass.
A looping shot also gets out_blocking/blocking_x10.mp4, the loop played ten times at the shot's frame rate. No agent
can watch it at real rate. When a rule asks for that viewing, either ask the author in QUESTIONS.md, naming that file,
or write in GATES.md that it is owed as "author viewing at sign-off". Never write that you watched it.

The shot format:
    {"rig": "v4", "fps": 24, "frames": 48, "loop": false,
     "keys": [{"f": 0, "name": "contact", "tangent": "auto", "root": [0, 0.95, 0], "footL": [-0.1, 0.08, 0.3]}, ...]}
Key whole poses: give every key the channels the pose needs. A channel a key leaves out carries over from the key
before; the first key's missing channels take the default stand. A short list takes the default tail.
A loop is made IN PLACE unless the author asked for root motion: the root does not travel, each planted foot slides
back under the body by the travel speed on every frame (speed / fps metres), and shot.json says
"in_place": {"speed_mps": <speed>}, so kei check measures it as it plays in a game, where the engine moves the
character. The loop's last key on f = frames repeats the first. Only when the author asks for root motion does the
cycle travel: then its last key on f = frames has the root and the feet moved on by one cycle.

The channels (metres, radians; x is the character's right, y up, z forward):
| channel | numbers | meaning |
|---|---|---|
| root | x, y, z | the pelvis in the world (standing y about 0.98) |
| yaw | one | heading of the body, + turns toward +x; the feet do not follow |
| pelvis | pitch, side | + pitch tips forward; + side drops the right hip |
| spine | pitch, side, twist | the whole spine; + pitch curls forward, + side bends right, + twist turns the chest right |
| spine1, spine2, spine3, spine4, spine5 | pitch, side, twist | extra bend of one segment |
| sq, neckS | one | spine and neck length scale (1 = rest) |
| armSL, armSR, legSL, legSR | one | arm and leg length scale (1 = rest) |
| neck, head | pitch, side, turn | + pitch looks down, + turn looks right |
| clavL, clavR | elev, fwd | + elev shrugs, + fwd rolls the shoulder forward |
| armL, armR | pitch, roll, twist | 0 hangs, + pitch swings forward and up, + roll lifts out to the side |
| elbowL, elbowR | flex, pron | + flex bends the elbow, + pron rolls the thumb in |
| handL, handR | flex, dev | + flex bends toward the palm, + dev toward the thumb |
| footL, footR | x, y, z, pitch, yaw | the ankle target in the world (standing y = 0.08), toe pitch, foot yaw |
| rollL, rollR | roll, bank, ballMax | < 0 heel strike, up to ballMax heel peel, past it toe-off; + bank: outer edge |
| toeL, toeR | one | extra bend of the toes |
| kneeL, kneeR | one | turns the knee about the hip to ankle line, + outward |
| ikL, ikR | x, y, z, w | the wrist goes to x, y, z with weight w (0 = the arm channels only) |
| poleL, poleR | x, y, z, w | with arm IK on, the elbow aims at the world point x, y, z, by weight w (0 = the arm channels' plane) |
| legFKL, legFKR | pitch, roll, twist, knee, w | an FK leg (thigh swing from the pelvis, knee bend) blended over the foot target by w (0 = IK leg) |
| fingersL, fingersR | thumb curl, oppose, then curl, spread for index, middle, ring, pinky | a curl bends the knuckle, middle joint and tip 1 : 2 : 1.5; presets in kei.hands: relaxed (the default), open, fist, point, ok, palm-up |

The commands:
- `kei pose <pose.json>` prints the joint positions of one pose (a JSON object of channels), to check a pose.
- `kei render <shot> blocking` draws out_blocking/shot.json stepped (`--mode step|linear|spline` to change it), on
  the shot's character (shot.json "character", else the Character line in PLAN.md, else the default); `--style stick`
  draws the stick figure instead, a diagnostic. Key the root and feet for that character's legs.
- `kei bake <shot> blocking` writes out_blocking/joints.json, the joints of every frame, for the checks.
- `kei render <shot> blocking --camera follow` rides the shot's even travel, so a travelling loop stays in frame
  and its seam can be judged (out_blocking/follow/); `--camera delivery` renders through the plan's locked camera
  (out_blocking/delivery/). Use these; do not write your own renderer.
- `kei poses <shot> blocking` writes the record of each key pose of the plan (out_blocking/poses/poses.json: support, weight
  side, centre of mass inside or out, lean, who holds each object) and draws out_blocking/poses/pose_sheet.png (ten keys a page; pose_sheet_2.png and on for more), four views
  per key with those facts. Kei writes it before each review too: the critics read it.
- `kei keys <shot> blocking set|offset|insert|copy|delete|shift ...` edits the keys in place, keeping every
  version in out_blocking/history/ and each edit in out_blocking/edits.json. Use it instead of an editing script.
- `kei probe <shot> blocking --frames 140-155 --joints elbow_l,hand_l,com` prints, per frame, the bends (elbow_l, elbow_r,
  knee_l, knee_r), a joint's position, move, speed and acceleration, and the feet's contacts; also `com_margin`,
  `ch:<channel>`, `palm_gap:<object>` and `<joint>@<joint>` (hand_l@spine_03); `--json <file>` saves it.
  Use it instead of writing a script to read the pass. It never changes a key.
- `kei try <shot> blocking set --frame 40 --channel spine --value 0.1,0,0` tests a `kei keys` edit on a copy and prints
  the flags it removes and adds; `kei sweep <shot> blocking --frame 40 --channel spine --from 0 --to 0.3 --steps 7`
  tries a range of values. Use them instead of a search script; neither changes the pass.
- `kei check <shot> blocking --explain <flag>` prints how a flag was measured: its frames, value and limits.

Objects the character handles (a crate, a ball) go in every pass's shot.json, once each; Kei places them on every
frame, draws them in every render and checks them, so you never track or draw an object yourself:
    "objects": [{"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0, 0.2, 0.5], "mass_kg": 35,
                 "attach": [{"f": 71, "to": "hands"}, {"f": 143, "to": "floor"}]}]
shape is box (size x, y, z), cylinder (diameter, height) or sphere (diameter), in metres; rest is the centre on frame
0. From an attach frame the object is held by "hand_l", "hand_r" or "hands" at the offset it had from the palm on
that frame, or let go ("floor") where it is. "yaw_deg" sets its heading; with "turn": "hands", an object held by both
hands turns with the line between the palms. kei check flags an object under the
ground, one that floats when nothing holds it, and a hand that takes it from more than 5 cm away.

A shot in Maya (the shot folder has maya/scene.ma) keeps the same shot.json: Kei's channels, or the rig's own
controls with `"rig": "maya"` and keys like `"l_foot_ik_ctl.translateY": 8.0` (degrees and the scene's unit). After
writing it, run `kei maya key <shot> <pass>`: it keys the controls in Maya, saves out_<pass>/scene.ma and writes
out_<pass>/joints.json from Maya for the checks (do not run `kei bake` on a Maya shot). `kei render <shot> <pass>`
then makes Maya previews of each view in out_<pass>/maya_views/. A locked channel is refused by name; a pose a limit
held back is listed in out_<pass>/maya_report.json.

A shot in Unreal (the shot folder has unreal/target.json) keeps the same shot.json, with `"rig": "unreal"` and keys
that name a control and a channel of the character's Control Rig, read from rig/unreal_rig.json, such as
`"foot_l_ik_ctrl.location.z": 8.0` (centimetres and degrees, Z up). You never talk to Unreal: after writing
shot.json, run `kei unreal key <shot> <pass>`. It keys the controls in Kei's own sequence in the open editor and
writes out_<pass>/joints.json from Unreal for the checks (do not run `kei bake` on an Unreal shot). A locked or
unknown channel is refused by name; a pose a limit held back is listed in out_<pass>/unreal_report.json.
A second performer of the same character (a ghost, a double, an echo the author asks for) goes in the same
shot.json. Name it under "performers": {"ghost": {"offset_cm": [x, y, z], "yaw_deg": d, "look": [...]}}, where
offset_cm is where it stands from the character's place (centimetres, Unreal axes), yaw_deg turns it, and look lists
the scalar material parameters that give it its look, each {"name", "value", "association" (global, layer or blend),
"layer" (the layer function's asset path, for a layer or blend parameter)}. Its keys carry its name as a prefix,
`"ghost/body_ctrl.location.x": 4.0`, on the same rig's controls; the character's keys keep no prefix. Kei makes its
materials under /Game/Kei/<shot>/looks/<name>/ as children of the character's own (which it never changes), keys it on
its own Control Rig track in the same sequence, and reads it back under "performers" in out_<pass>/joints.json. The
renders draw it in a lighter colour behind the character. Only the character is checked and delivered: the performer
is part of the staging. Once the author signs the shot off, the bake makes the performer's own animation too, as a
reference for effects. Act the two together: where each one looks, who leads and who answers, and the
performer's own timing.
The fingers and toes come back too: out_<pass>/hands_toes.json gives each finger joint's curl (positive closes it
toward the palm, negative bends it backward) and each toe's lift against the foot, per frame, with flags for a finger
bent backward and for toes bent down (a flick in the air, or digging into the floor). Read it before you ask the
author about the hands or toes: ask only what the numbers cannot show.
A pose that already exists in the project (the character's idle the shot starts from, the last frame of the clip
before it) is never searched for by keying probes: run `kei unreal pose <shot> --anim <asset path> --frame <n>`.
The Control Rig solves that frame itself, fingers and toes included, and Kei writes
rig/pose_<anim>_f<n>.json: "keys" holds every channel's value in the units shot.json keys in, so the key is
{"f": <frame>, "tangent": ..., **keys}, unchanged. Key every channel of it, not a subset, and do not adjust it
toward a number you measured elsewhere. Its "check" says how closely the rig reached the animation; when
"matches" is false, tell the author before you build on the pose.
Each flag in body_check.json is "hard" or "soft". A soft flag marked "note" (inside the character's style range,
rig/style.json, or under a pushed register) is the character's own way of standing: keep it, and do not pull the pose
toward generic realistic mechanics. A pose the author gave, or one taken from their clips, is never corrected toward the
checks. Hard flags are fixed or declared as always.
Kei stands the character on the floor at the open level's first Player Start, not at the origin: unreal/placed.json
gives the level, the spot ("at_cm", world centimetres) and the sequence. Any camera or capture of the mesh you set up
in the editor aims at that spot, and you read placed.json again after each new sequence, since the level can change.
