Run every check on the latest pass: `kei check <shot> p<n>` measures out_p<n>/shot.json on the shot's character and
writes out_p<n>/body_check/body_check.json, newer than its shot.json. It measures the contacts, foot slide, balance
(the centre of mass over the support), joint ranges and arcs, and lists each flag with its frames and the threshold
it crossed. Fix each flag at a key and run `kei check` again, or declare it with a reason (a fall, a stylised pose).
The same command writes out_p<n>/principles/principles.json: the twelve principles, each "clean", "flags" or
"unchecked". Read every section. Each flag is fixed in a new pass, or declared in GATES.md under "## Declared" as
"- <flag id>: <reason>"; the gate refuses an open flag. An "unchecked" principle (appeal, exaggeration without a
style range) is judged by you on the frames and the playback, and you say how in the self-review.
