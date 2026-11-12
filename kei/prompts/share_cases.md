## Contract: two cases for a shared lesson

A person learned the lesson below on their own shot. Their shot stays on their machine. Your job is to show the
lesson again on Kei's own open character, `kei`, so that anyone can judge it.

Write three files in this folder and nothing else:

- `cases/fails/shot.json`: a short shot (rig "v4", "character": "kei") that breaks the lesson. Keep it small: a few
  keys, at most 48 frames.
- `cases/passes/shot.json`: the same shot with only what the lesson asks changed, so that it keeps the lesson.
- `cases/check.txt`: one word, the `kei check` check that measures the lesson (contacts, hover, foot_slide, balance,
  trunk_lean, joint_ranges, knee_snap or arcs), or `none` when no check measures it (a lesson of taste).

Kei measures both cases with `kei check` on `kei`. With a check named, the failing case must raise that check and the
passing case must not, or the bundle is refused. Run `kei check` yourself to see it before you stop.

Never copy anything from the person's shot: no names, no paths, no notes about their character. Only the lesson
text below is shared, with your two cases.
