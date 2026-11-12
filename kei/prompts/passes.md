Refine in passes: breakdowns, then spline, then polish. Each pass is a new folder out_p<n>/ holding its shot.json; never
overwrite an earlier pass. After each pass, run `kei render <shot> p<n>` (spline by default) and look at the frames,
the key sheet and out_p<n>/playback.mp4 (playback.gif when ffmpeg is missing), and run `kei bake <shot> p<n>` so the
checks read out_p<n>/joints.json. Add to GATES.md "## Breakdowns gate: pass", "## Spline gate: pass" (naming the
curves image you checked, which must exist) and "## Polish gate: pass". If animating shows the plan was wrong, update
the plan sheet and say what changed and why.

The shot format, the same as blocking:
    {"rig": "v4", "fps": 24, "frames": 48, "loop": false,
     "keys": [{"f": 0, "name": "contact", "tangent": "auto", "root": [0, 0.95, 0], "footL": [-0.1, 0.08, 0.3]}, ...]}
Key whole poses: a breakdown is a pose too, with every channel it needs. A channel a key leaves out carries over from
the key before; the first key's missing channels take the default stand. "tangent" is "auto" (from the neighbour
keys) or "flat" (eases in and out of the key). A looping cycle that travels keys its last key on f = frames with the
root and the feet moved on by one cycle; the seam is then not eased by accident.

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
| fingersL, fingersR | thumb curl, oppose, then curl, spread for index, middle, ring, pinky | a curl bends the knuckle, middle joint and tip 1 : 2 : 1.5; presets in kei.hands: relaxed (the default), open, fist, point, ok, palm-up |

The commands:
- `kei pose <pose.json>` prints the joint positions of one pose (a JSON object of channels), to check a pose.
- `kei render <shot> p<n>` draws out_p<n>/shot.json (`--mode step|linear|spline`, spline by default) on the shot's
  character; `--style stick` draws the stick figure instead, a diagnostic.
- `kei bake <shot> p<n>` writes out_p<n>/joints.json, the joints of every frame, for the checks.
- `--camera follow` (ride the even travel) and `--camera delivery` (the plan's locked camera) render a travelling
  shot so it can be judged, into out_p<n>/follow/ and out_p<n>/delivery/.
- `kei check <shot> p<n>` measures the pass (contacts, foot slide, balance, joint ranges, arcs).

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
The fingers and toes come back too: out_<pass>/hands_toes.json gives each finger joint's curl (positive closes it
toward the palm, negative bends it backward) and each toe's lift against the foot, per frame, with flags for a finger
bent backward and for toes bent down (a flick in the air, or digging into the floor). Read it before you ask the
author about the hands or toes: ask only what the numbers cannot show.

An author's note may carry a feedback pose: an animator posed the correction on a Maya layer named feedback, and Kei
saved it as feedback/<n>/pose.json with the author's reason. Its targets (control, frame, value) are listed with the
note. Make a new pass that reaches each target at its frame, on the rig's controls (`"rig": "maya"` keys name them
directly), within 1 deg or 0.5 cm, and keep the rest of the motion working around it. The reason says why; follow it
where the pose alone does not say enough. The check reads the newest pass's keys and sends it back naming any control
it missed.
