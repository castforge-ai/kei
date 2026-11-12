# Live check: a correction posed on a feedback layer (about 5 minutes)

This check runs in a real Maya, by a person. The automatic tests use a stand-in for Maya; this one shows that the
command reads a real layer, records the note, and leaves your layer and your file as they were.

You need: Maya with the Kei host (`kei maya shelf`), and a Maya shot that waits for your sign-off (`kei status
<shot>` says `needs_approval`) with a pass keyed on Kei's rig by this version of Kei, for example `out_p1/scene.ma`.
Keying the pass (`kei maya key <shot> p1`) printed `pose corrections on layer feedback_p1, then run: kei maya
feedback <shot>`.

1. **Note the starting point.** Run `kei status <shot>` and keep the history length in mind. In a terminal, note the
   hash of the scene you will open: `certutil -hashfile <your scene>.ma SHA256` (or `shasum -a 256` elsewhere).
2. **Open the pass in Maya.** Open the scene the shot works in (the open session) or `out_p1/scene.ma`. Look at the
   Animation Layers panel: note every layer, and which ones are muted.
3. **Find the layer Kei made.** In the Animation Layers panel, `feedback_p1` is there, empty, just above Kei's
   layer `kei_p1` (at the top for a pass keyed in the background, which has no Kei layer), and it is the selected
   layer. You make no layer yourself.
4. **Pose the correction.** Select `kei:l_leg_pv_ctl` (the left knee pole). Set a key at frames 4 and 8 as it is,
   then at frame 6 move it about 5 cm toward the character's left (Maya's +X) and set a key. Check that the keys went
   on `feedback_p1` (its curve, not `kei_p1`'s). Do not save the scene.
5. **Run the command.** In the shot folder run `kei maya feedback <shot>`. Expect a line close to
   `knee_l bend turns 7 deg outward at f6 (the knee pole moves 5.0 cm)`, then before and after previews in
   `feedback/1/before` and `feedback/1/after`. Watch both: the after shows your knee.
6. **Give the sentence.** When Kei asks why, type one sentence, for example `The knee must open out more as the
   weight lands.` When it asks for the scope, answer `this` (the default).
7. **See the note recorded.** Expect `note 1 recorded word for word for this shot` and a lesson line with `(this shot)`. Check:
   - `feedback/1/note.json` holds your sentence exactly as you typed it;
   - `feedback/1/pose.json` lists `kei:l_leg_pv_ctl`, `translateX`, frame 6, its value and its offset;
   - `kei status <shot>` says the shot is back at `passes`, and the new local lesson holds your sentence
     with `scope: this shot` and no control name or value (the pose stays in the shot).
8. **See the layer untouched.** In Maya, the `feedback_p1` layer is still there, not muted, with its keys, and
   every other layer has the mute state you noted in step 2. In the terminal, the scene file's hash is the same as in step 1
   (for the open session, Maya shows no new save: Kei only exported a copy into the shot's `maya/` folder).

Optional, 1 more minute: rename the layer to `fixes` and run the command again. Expect "no correction found" and
nothing recorded. Rename it back afterwards.

Report the result with the Maya version and anything that differed from the expected lines.
