Refine in passes, each with its own job, in this order. Each pass is a new folder out_p<n>/ holding its shot.json;
never overwrite an earlier pass. A pass may take more than one try; the order of the jobs does not change.
1. Breakdowns and spline: timing and spacing only. Breakdowns are new poses that shape each move (not in-betweens), the
   spacing eases in and out, the paths arc. Gates "## Breakdowns gate: pass" and "## Spline gate: pass" (naming the
   curves image you checked, which must exist).
2. Overlap: offset every chain from the blocking. Name the lead of each move and the order of the parts (OVL38); the
   driver goes first and each part down the chain trails it a frame or more (OVL3, OVL24); the arms drag behind a
   trunk turn and catch up; left and right never move in unison (OVL30); no extreme of every part on the same key.
   Gate "## Overlap gate: pass", listing per move the lead and the frames each part peaks on.
3. Follow-through and secondary action: at every stop the parts land one after another, the followers overshoot and
   settle (OVL9, OVL18, OVL19); a hold keeps moving (TIM34); the hands, fingers and breath have their own life
   below the main action (OVL33). Gate "## Follow-through gate: pass", listing per stop the order the parts land in.
4. Polish: arcs, contacts, the author's notes, the last details. Gate "## Polish gate: pass".
After each pass, run `kei render <shot> p<n>` (spline by default) and look at the frames, the key sheet and
out_p<n>/playback.mp4 (playback.gif when ffmpeg is missing), and run `kei bake <shot> p<n>` (Kei's own rig) so the
checks read out_p<n>/joints.json. Then run `kei check <shot> p<n>`: besides the body checks, it measures the twelve
principles (squash and stretch, anticipation, staging, pose to pose, overlap, slow in and out, arcs, secondary action,
timing, exaggeration, solid drawing, appeal) into out_p<n>/principles/principles.json, each flag with an id, its
frames and what to change. Every flag is fixed in the next pass, or declared in GATES.md under "## Declared" as
"- <flag id>: <reason>" when the shot means it (a hard stop on an impact, a stylised pose the author asked for). The
gate refuses the stage while a flag of the newest pass is neither fixed nor declared. A pass that only smooths the
blocking (every extreme still on a blocking key) is flagged pose_to_pose: it is not a pass yet.
If animating shows the plan was wrong, update the plan sheet and say what changed and why.

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
| poleL, poleR | x, y, z, w | with arm IK on, the elbow aims at the world point x, y, z, by weight w (0 = the arm channels' plane) |
| legFKL, legFKR | pitch, roll, twist, knee, w | an FK leg (thigh swing from the pelvis, knee bend) blended over the foot target by w (0 = IK leg) |
| fingersL, fingersR | thumb curl, oppose, then curl, spread for index, middle, ring, pinky | a curl bends the knuckle, middle joint and tip 1 : 2 : 1.5; presets in kei.hands: relaxed (the default), open, fist, point, ok, palm-up |

The commands:
- `kei pose <pose.json>` prints the joint positions of one pose (a JSON object of channels), to check a pose.
- `kei render <shot> p<n>` draws out_p<n>/shot.json (`--mode step|linear|spline`, spline by default) on the shot's
  character; `--style stick` draws the stick figure instead, a diagnostic.
- `kei bake <shot> p<n>` writes out_p<n>/joints.json, the joints of every frame, for the checks.
- `--camera follow` (ride the even travel) and `--camera delivery` (the plan's locked camera) render a travelling
  shot so it can be judged, into out_p<n>/follow/ and out_p<n>/delivery/.
- `kei check <shot> p<n>` measures the pass: body_check.json (contacts, foot slide, balance, joint ranges, arcs)
  and principles.json (the twelve principles).
- `kei poses <shot> p<n>` writes the record of each key pose of the plan (out_p<n>/poses/poses.json: support, weight
  side, centre of mass inside or out, lean, who holds each object) and draws out_p<n>/poses/pose_sheet.png (ten keys a page; pose_sheet_2.png and on for more), four views
  per key with those facts. Kei writes it before each review too: the critics read it.
- `kei probe <shot> p<n> --frames 140-155 --joints elbow_l,hand_l,com` prints, per frame, the bends (elbow_l, elbow_r,
  knee_l, knee_r), a joint's position, move, speed and acceleration, and the feet's contacts; also `com_margin`,
  `ch:<channel>`, `palm_gap:<object>` and `<joint>@<joint>` (hand_l@spine_03); `--json <file>` saves it.
  Use it instead of writing a script to read the pass. It never changes a key.
- `kei try <shot> p<n> set --frame 40 --channel spine --value 0.1,0,0` tests a `kei keys` edit on a copy and prints
  the flags it removes and adds; `kei sweep <shot> p<n> --frame 40 --channel spine --from 0 --to 0.3 --steps 7`
  tries a range of values. Use them instead of a search script; neither changes the pass.
- `kei check <shot> p<n> --explain <flag>` prints how a flag was measured: its frames, value and limits.
- `kei keys <shot> p<n> set|offset|insert|copy|delete|shift ...` edits the keys (`--frame`, `--frames 40-60`,
  `--channel root`, `--value` or `--by`, `--from`; `--to p<n+1>` writes a new pass). Kei keeps every version in
  out_p<n>/history/ and logs each edit in out_p<n>/edits.json. Use it instead of writing a script that edits keys;
  `shift` retimes and moves the objects' attach frames with the keys.
- `kei trails <shot> p<n-1> p<n> --parts hand_l_tip,head --frames 140-160` draws the parts' paths with a dot per
  frame (the spacing chart), the passes overlaid in colours, into out_p<n>/trails/trails.png. Look at it instead of
  drawing your own compare sheet.
- `kei curves <shot> p<n> --channels spine,armL` draws a curve image per channel (out_p<n>/curves/), the graph
  editor's view: dips between keys, overshoots and flat runs. `kei render <shot> p<n> --style stick --onion 2` draws
  each frame with the two before and after as pale figures.
- `kei rule <ID> [<ID> ...]` prints a rule of the book in full.
Kei measures each pass against the one before and writes out_p<n>/refinement.json (keys, keyed share, mean and
largest joint change, frames that changed). A pass that changes nothing is not a pass, and a long pass keyed on
nearly every frame is sampled, not animated (WFL26): both fail the gate. Keep the keys on poses and breakdowns.
Objects stay in each pass's shot.json as the blocking declared them ("objects", with their "attach" frames): move an
attach frame when the timing changes, never draw or track an object yourself.

A shot in Maya (the shot folder has maya/scene.ma) keeps the same shot.json: Kei's channels, or the rig's own
controls with `"rig": "maya"` and keys like `"l_foot_ik_ctl.translateY": 8.0` (degrees and the scene's unit). After
writing it, run `kei maya key <shot> <pass>`: it keys the controls in Maya, saves out_<pass>/scene.ma and writes
out_<pass>/joints.json from Maya for the checks (do not run `kei bake` on a Maya shot). `kei render <shot> <pass>`
then makes Maya previews of each view in out_<pass>/maya_views/. A locked channel is refused by name; a pose a limit
held back is listed in out_<pass>/maya_report.json.

A shot in Blender (the shot folder has blender/) keeps the same shot.json, with Kei's channels. After writing it, run
`kei blender key <shot> <pass>`: it keys the pass's key poses in Blender (the legs on IK), saves out_<pass>/scene.blend
and writes out_<pass>/joints.json from Blender for the checks (do not run `kei bake` on a Blender shot). Between keys
Blender plays its own interpolation: when the checks flag an in-between Kei's own rig would not, add a breakdown key
there. `kei render <shot> <pass>` makes Blender previews of each view in out_<pass>/blender_render/.

A shot in Unreal (the shot folder has unreal/target.json) keeps the same shot.json, with `"rig": "unreal"` and keys
that name a control and a channel of the character's Control Rig, read from rig/unreal_rig.json, such as
`"foot_l_ik_ctrl.location.z": 8.0` (centimetres and degrees, Z up). You never talk to Unreal: after writing
shot.json, run `kei unreal key <shot> <pass>`. It keys the controls in Kei's own sequence in the open editor and
writes out_<pass>/joints.json from Unreal for the checks (do not run `kei bake` on an Unreal shot). A locked or
unknown channel is refused by name; a pose a limit held back is listed in out_<pass>/unreal_report.json.
Before the critics review an Unreal pass, Kei has the editor render it on the character's real mesh, every frame,
from a side, a three quarter and a low feet view (out_<pass>/mesh_<view>.png, one sheet per view, frames labelled;
full size in out_<pass>/mesh/<view>/). The critics judge those frames first: toes or feet through or off the floor,
folded toes, pops, frozen limbs, stalls and sliding feet on the mesh come back to you as notes with their frames.
To see them yourself before the review, run `kei unreal render-mesh <shot> <pass>` (a few minutes) and open the sheets.
From p2 on, each pass is a layer of the one before it. Start the pass's shot.json from the previous pass's (a copy,
every frame keyed, the same tangents) and change only the channels and the frames the pass's job or the author's
note bears on; leave every other value exactly as it was. `kei unreal key` then copies the previous pass's sequence,
writes only the differences on an additive layer over those frames, and merges it down: what was already right
cannot drift. out_<pass>/unreal_report.json "layer" lists the controls and frames each pass changed; when a pass
changes the tangents, the length, or a switch, it says why the pass was keyed whole instead. The previous pass's
sequence stays as it was, for before and after.
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
Each limb has an IK/FK switch on the Control Rig, <limb>_fk_ik_switch (arm_l, arm_r, leg_l, leg_r; true is IK). To change a limb's mode without a pop, never key the switch by hand: run kei unreal switch <shot> <pass> --limb <limb> --to ik|fk --frame <f>, which writes a matched switch into your pass, then kei unreal key.

An author's note may carry a feedback pose: an animator posed the correction on a Maya layer named feedback, and Kei
saved it as feedback/<n>/pose.json with the author's reason. Its targets (control, frame, value) are listed with the
note. Make a new pass that reaches each target at its frame, on the rig's controls (`"rig": "maya"` keys name them
directly), within 1 deg or 0.5 cm, and keep the rest of the motion working around it. The reason says why; follow it
where the pose alone does not say enough. The check reads the newest pass's keys and sends it back naming any control
it missed.
