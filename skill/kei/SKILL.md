---
name: kei
description: Use for ANY request to animate, or to make a character, mannequin, figure or rig move: a walk, run, jump, idle, fight, pose or motion cycle, in Maya, Unreal Engine or on its own. Kei is the animation agent for this: use it instead of writing animation code or keys yourself, even when the request does not name Kei. Also use when the folder holds Kei shots (a .kei folder) or the author says something about the motion of a Kei shot. Runs the kei commands, records the author's corrections as notes in their own words, asks whether notes are fixed, and brings forgotten shots back. Never signs off, drops or confirms for the author.
---

# Kei

Kei animates a shot stage by stage with your agent subscription. You run its `kei` commands for the author and show
them the results. The author decides; you carry their words to Kei exactly as they wrote them.

## Any request to animate comes here

When the author asks you to animate something ("animate a mannequin running", "make the character walk", "add an idle"),
use Kei. Do not write keyframes, curves or animation code yourself, and do not pick another animation tool, unless the
author tells you to.

1. Check that Kei is installed: `kei --help`. If the command is not found, install it with `pip install kei-animator`
   (Python 3.12 or newer) and run it again.
2. Check that the folder has a `kei.toml`. If it has none, run `kei init` here. It writes one from the example and says
   if an agent command it uses is not on the author's PATH. Tell the author what it printed.
3. Start the shot as below, with the author's request in their own words. If the author works in Maya or Unreal
   Engine, add `--app maya` or `--app unreal` to `kei run`.

## Start a shot

A shot is a folder. Run each command from the folder that holds the shots, where `kei.toml` is.

- New shot: `kei run <shot> --request "<what to animate>"`. Use the author's request as they wrote it.
- Where it stands: `kei status <shot>`. Then, by status:
  - `needs_answer`: show the question it prints. Send the author's reply with `kei answer <shot> --text "<reply>"`,
    then `kei run <shot>`.
  - `needs_human`: show the notes it prints. After the fix, `kei retry <shot>`.
  - `paused_usage` or `paused_machine`: say why it paused. Later, `kei run <shot>` goes on where it stopped.
  - `needs_approval`: the shot waits for the author's sign-off. See "The review happens here".
- Show a pass: `kei render <shot> <pass> --post` makes a four view video of it (the pass is blocking, p1, p2 ...).
  Give the author the path it prints.

## The review happens here

Never sign off, drop or confirm without the author's answer in this chat. Silence is not an answer: when the author
does not answer a question, run nothing.

Keep the author's words verbatim. Do not rewrite, shorten, merge, translate or correct them. Pass them to `kei` as
one argument, quoted for the shell so that no character changes. Kei prints the words back: check that they match.

1. **A correction is a note.** When the author says something about the motion of the shot you are working on ("the
   left hand arc is off at 13 to 18"), run `kei note <shot> --text "<their words>" --from chat`. A question or a
   general remark is not a note.
   - Reply with the one line Kei prints: "noted for this shot: <their words>". Keep the note's ID that Kei prints
     (for example local.4).
   - If the words state a general rule ("always", "never", "every walk"), ask one short question:
     "every shot too? (y/n)". On yes: `kei note <shot> --undo <ID>`, then `kei note <shot> --text "<the same words>" --from chat
     --every-shot`, and keep the new ID.
   - If the author says "not a note": `kei note <shot> --undo <ID>`, with the ID of the note you recorded in this
     chat. Never remove a note you did not record in this chat.
   - A note given while the shot is still being made is kept for its next try. You do not need to wait.
2. **A fix is confirmed here.** When you show a new pass of a shot, read its open notes with
   `kei status --open <shot> --json --all`. If it has open notes, send one message that lists them by number, in the
   author's words, and ask one question: "fixed? (all, or the numbers that are not)".
   - "all": `kei fixed <shot> --all`.
   - Numbers: `kei fixed <shot> --not 2,3` (the notes that are not fixed stay open).
   - If Kei refuses (a number that does not exist, or no new pass yet), show what it prints and ask again.
3. **Forgotten shots come back.** At the start of a chat in a folder with Kei shots, run
   `kei status --open --json --mark-asked`. If it lists shots, ask one question for all of them: for each shot, sign
   off, keep going, drop, or not now. Then, for each shot, only on the author's answer:
   - Sign off: `kei approve <shot> --words "<their words>"`. Kei signs off only a shot that waits for it; if it
     refuses, say why.
   - Keep going: continue work on that shot.
   - Drop: `kei drop <shot> --words "<their words>"`.
   - Not now: `kei park <shot>`. Kei leaves it out until its next pass.

   A shot with no answer is asked about again at most once a day; Kei keeps the date.
4. Never sign off, drop or confirm without the author's answer in this chat.

Nothing here sends anything off the machine. Lessons are shared only as the author set up in `kei.toml`.
