Write PLAN.md for this shot. It states the brief (what is asked, who moves, what they want, how heavy it is, the
frame budget) and has a line that starts "Idea sentence:" with the one sentence the shot must say.
If the request is unclear, or you cannot tell which character or rig to use, write your questions in QUESTIONS.md
and stop. Ask at the start whatever the start can settle; any later stage may still ask what only the author can
answer.
When the rule book lists subject topics below, add a line "Subjects: <names>" to PLAN.md naming every subject this
shot touches (a walk carrying a box: locomotion, actions, arms-hands). A shot with a character that has a want or an attitude,
an idle breaker above all, always names personality. When unsure, include the topic; "Subjects: all"
is always allowed. Every later stage gets the principles plus these subjects.
Ask the author for the register of the shot, and write their answer on a line "Register: realistic", "Register:
stylized" or "Register: pushed" in PLAN.md. Never guess it: with no answer, leave the line out (Kei then judges as
realistic). Realistic keeps the body checks' realism rules; stylized judges them against the character's own clips;
pushed makes the soft body flags (balance, trunk lean, knee and elbow range, arc kinks, a wide stance, a neck bend, a
straight arm) notes, never faults. When the author pushes only some beats, name them on the same line, such as "Register:
pushed f61-120, f150-167": the rest of the shot is judged as realistic. Spacing pops, wobble and jolts stay faults
in every register, and so do the hard flags: contacts, hover, foot slide, a knee bending backward, reach, a knee snap, locked knees.
For a character with clips of their own in the Unreal project, name the clips most like this shot in PLAN.md on a
line "Style clips: <asset path>, <asset path>", and run `kei unreal style <shot> --anim <path> [--anim <path> ...]`.
It writes rig/style.json: how far each soft check goes in their own animation. A soft flag inside that range is a
note with the clip that shows it, not a fault, and the exaggeration check compares each move's size with theirs.
Choose the character who performs the shot and write it on a line "Character: <name>" in PLAN.md. With no line, the
configured default performs (Kei unless kei.toml says otherwise; the line below names it). Choose Keira when the brief asks for her, or when the shot needs a different
build from Kei's. The characters:
- kei: 1.71 m, broad shoulders, a deep chest, narrow hips, sturdy limbs and hands
- keira: 1.71 m, shoulders narrower than her pelvis, softer limb tapers, long lower legs, a lighter build
A later change of the character is a plan change, and the critics review it.
