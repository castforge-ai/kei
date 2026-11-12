Run every check on the latest pass: `kei check <shot> p<n>` measures out_p<n>/shot.json on the shot's character and
writes out_p<n>/body_check/body_check.json, newer than its shot.json. It measures the contacts, foot slide, balance
(the centre of mass over the support), joint ranges and arcs, and lists each flag with its frames and the threshold
it crossed. Fix each flag at a key and run `kei check` again, or declare it with a reason (a fall, a stylised pose).
