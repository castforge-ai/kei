Plan the shot BEFORE any key goes into it. Add an X-sheet table to PLAN.md (its header starts "| frames |").

Write plan/plan.json. Each key pose has a frame, a function, a kind, an intent, a note and a drawing:
{"keys": [{"f": <frame>, "function": "<pose function: contact, down, passing, antic, apex...>",
           "kind": "key|extreme|breakdown", "intent": "<one line: what the pose says>",
           "judged_in": "<the view you judge it in: side, front, three quarter or back>",
           "note": "<what this pose must show>",
           "drawing": {"lines": [[x1, y1, x2, y2], ...], "action": [[x, y], ...], "com": [x, y]}}],
 "arcs": {"<main part>": [[<frame>, x, y], ...]}}

A key may add "views": {"front": <drawing>, "top": <drawing>}: the same pose from the front (x is screen right) and
from above (y is forward). Kei draws them beside the key's side view. Never add a second key on the same frame to
show another view.

A drawing is the pose seen from the side, in the rig's proportions, y up, in one unit for the whole plan: "lines"
are the body's parts as segments, "action" is the line of action, "com" is the centre of mass. "arcs" are the planned
paths of the main parts, a point per frame you plan.

A loop is planned IN PLACE unless the author asked for root motion: draw each pose where the body stands with the
root at the origin (the planted foot drifts back), and put "loop": true and "in_place": {"speed_mps": <speed>} in
plan.json. Ask about root motion only when the brief needs the clip to drive the character.

When the shot has a locked delivery camera, put it in plan.json as "camera", in Kei's format, and Kei renders
through it (`kei render <shot> <pass> --camera delivery`), so you never write your own renderer:
"camera": {"yaw_deg": 0, "pitch_deg": 0, "target_m": [x, y, z], "lens_mm": 50, "distance_m": 6.5, "aspect": "16:9",
           "follow": true}
yaw 0 looks at the character's right side, 90 at its front; "span_m" (the frame's height in metres) replaces lens_mm
and distance_m for a camera with no perspective; "follow" rides the shot's even travel.
When the shot has a sound track (sound/sound.json, from kei sound), time the keys to it: sound/XSHEET.md is the sound
column of the X-sheet (the level per frame, the beats marked B, the phrases), sound/waveform.png draws it, and
kei keys <shot> <pass> snap --by 2 moves keys onto the nearest beats.
When the shot needs the camera to move (a push in, a pan to a reaction, a cut), add "keys" to the camera:
"keys": [{"f": 0}, {"f": 40, "lens_mm": 70}, {"f": 72, "yaw_deg": 60, "cut": true}]. Each key changes some settings
from its frame; the camera eases between keys, and "cut": true starts a new setup on that frame. The delivery render
writes framing.json with its staging notes per setup (out of frame, a short setup, a cut across the line, a small
figure): read them before you call the camera done.

The physical facts of a pose (planted feet, weight side, centre of mass over the support, lean) are Kei's to measure
on each pass (`kei poses`): write the intent and the acting in the key, not those facts.

Kei draws plan/plan_sheet.png from these drawings after every stage: a panel per key pose and one panel with every
arc. The sheet is Kei's: change plan.json, never the PNG.
Every later pass is compared with this sheet.
