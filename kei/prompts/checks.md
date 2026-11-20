Run every check on the latest pass: `kei check <shot> p<n>` measures out_p<n>/shot.json on the shot's character and
writes out_p<n>/body_check/body_check.json, newer than its shot.json. It measures the contacts, foot slide, balance
(the centre of mass over the support), contact timing (a foot that lifts while it still carries over half the weight,
or takes most of it on the frame it lands), joint ranges and arcs, and lists each flag with its frames and the threshold
it crossed. Fix each flag at a key and run `kei check` again, or declare it with a reason (a fall, a stylised pose).
The gate refuses a hard flag that is neither fixed nor declared in GATES.md under "## Declared" as
"- <check>.<part>.f<first frame>: <reason>" (kei check --explain prints the id, such as foot_slide.body.f40).
A flag marked "note" (a soft flag inside the character's style range, rig/style.json, or under PLAN.md's
"Register: pushed") is not a fault: list it in the self-review as the character's own, with the clip it names. Hard
flags (contacts, hover, foot slide, a knee bending backward, reach, a knee snap, locked knees) and spacing pops, wobble
and jolts are faults in every register, and a pushed register that names its beats covers only those frames.
The same command writes out_p<n>/principles/principles.json: the twelve principles, each "clean", "flags" or
"unchecked". Read every section. Each flag is fixed in a new pass, or declared in GATES.md under "## Declared" as
"- <flag id>: <reason>"; the gate refuses an open flag. An "unchecked" principle (appeal, exaggeration without a
style range) is judged by you on the frames and the playback, and you say how in the self-review.
