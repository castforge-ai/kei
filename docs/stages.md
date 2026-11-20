# The twelve stages

Every shot goes through the same stages, in this order. Each stage has a gate that reads what the stage wrote. Plan,
blocking and passes also go to the critics, and a pass made later goes back to them.

| # | Stage id | Name | What it leaves |
|---|---|---|---|
| 1 | `brief` | Brief | the request restated, the idea sentence, the character, the topics the shot needs |
| 2 | `rig` | Rig evaluation | what the rig can do and where its limits are |
| 3 | `weight` | Weight evaluation | the character's mass and weight class |
| 4 | `understanding` | Understanding score | how well the action is understood before any key |
| 5 | `references` | Reference search | vetted reference for the action |
| 6 | `study` | Study | the reference measured, and where the shot departs from it |
| 7 | `plan` | Plan | the key poses with their frames in `plan/plan.json`, the X-sheet, a plan sheet, the arcs |
| 8 | `blocking` | Blocking | the key poses stepped in `out_blocking/shot.json`, four views, a playback and the pose records |
| 9 | `passes` | Breakdowns, spline and polish | each refined pass in its own `out_p<n>/` folder |
| 10 | `checks` | All the checks | `kei check` on the newest pass: contacts, balance, arcs, the principles, posing, objects |
| 11 | `self_review` | Self-review | what was seen, frame by frame, before anyone else looks |
| 12 | `deliver` | Delivery | the shot, the report and the lessons it taught |

`kei note <shot> --stage <stage id>` sends a delivered shot back to a stage. `kei status <shot>` names the stage the
shot is at. `KEI_RECORD.md` in the shot folder is Kei's own record of each stage: tries, each pass's hash and the flag
counts.
