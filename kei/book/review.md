# Review and checks

kind: principle

How Kei reviews its own work: the views it looks through, the order of looking and measuring, what a check can
measure and what only the eye can judge, the self-review that stands before any shot is shown, and how a fault that
slipped past a gate becomes a new check.

### REV1. The eye decides; numbers only point
stages: checks, self_review, deliver

A shot is good when it looks good in motion, not when it scores well. Passing every check is not good posing: a pose
can clear every measurement and still be a bad shape, and more than once a version with better numbers looked worse
on screen. Never present a measured score as proof of quality. Never make a change whose only reason is a check, a
score or a number: never move a key just to shift a number or silence a flag, and never add a key whose job is to
mask a corner from a measurement. Never loosen a hard limit to pass; a limit changes only when the intent changes,
and the reason is written. Never force a film timing onto a realistic game shot to satisfy a check. Every change
states what was seen, in which camera and on which frames.

When a check disagrees with the words of the person who signs off the shot, build the words and declare the check.
Never sign off a matter of taste yourself, and never call a shot done without the full look at every frame.

### REV2. When a check fights the stated intent, build the intent
stages: passes, checks, self_review

A check can reward the wrong motion on a given rig, and some checks reward faults outright: fixed overlap offsets, a
flat arc limit, easing on a cycle, or a line-of-action score that grows with total bend and so rewards hooks and
curls. One example: a check that wanted the chest to come closer to the pelvis after each contact, on a rig where a
forward fold pushes them apart, so it rewarded a backward rock that read as a pump. Adding a move only to shorten a
measured value, such as a quick chest bump, reads as a pump in the same way. Tuning keys to pass a threshold rewards
the wrong thing.

Build the motion that the brief or the words of the sign-off note describe. When a check disagrees with the eye,
record it as a known disagreement in the review notes, with its value and the reason, and file the check itself as a
fault in the tool. The motion is never bent to satisfy it.

### REV4. Review the real images, and trust none unseen
stages: passes, checks, self_review

Critique from the renders themselves: contact sheets, onion skins, motion trails and short loops. Open every new image
once before it is used as evidence. A camera that crops the subject, a label left over from an older version, or a strip
whose cells are narrower than their content (so each frame bleeds into its neighbour and fakes a shape) all mislead. A
sign error inside a measurement can pass every number and only show on mesh captures.

### REV5. Scrub at three scales, then play it at speed
stages: blocking, passes, checks

From blocking on, scrub to and fro across roughly a fifth of a second (about 5 frames at 24 fps) on either side of
every key and contact, hunting for a pop or a frame where nothing happens. Then hop through the shot half a second at
a time (12 frames at 24 fps); from each hop to the next the main action must have advanced, without stalling and
without a sudden leap. Then go frame by frame to follow the secondary motion and confirm each follower trails its
driver. Finally play the whole shot at speed, looping, slowed down and backwards.

### REV7. Polish from a written, ranked list
stages: passes, self_review

Before any change, and above all after a break, render it and watch it looping, with frame numbers on screen and fresh eyes.
Write down everything that catches the eye with its frame number and the principle it breaks. Rank the list and work
it from the top, then render and watch again. Repeat until the list is empty or time runs out; whatever remains becomes
the known-issues record that travels with the shot. When something looks off, try changing its timing before changing its pose. When the
stepped keys turn into splines, convert everything in one go and write the list before touching a single key.

### REV8. When looking stops helping, build the curve from physics
stages: passes

If repeated viewing no longer shows what is wrong with the centre of mass, stop guessing. Shape its curves from what the
physics demands (a parabola in flight, a sharp change at a push), then render and fix whatever the render reveals.

### REV9. Keep a short list of what is being learned
stages: passes, self_review

Hold an active list of five to ten items that are new and not yet habit. Read it first on every pass, on top of the
normal gates, and drop an item once it has become automatic. This list adds to the gates; it never replaces one.

### REV10. Every check runs on every piece of work
stages: checks, self_review

Each shot, each pass and each kind of action runs the whole body check with all of its items, the motion items
included: overlap, locked elbows, parts that stop together, flight physics and landing absorption. A shot narrows the
checks only by declaring its phases (wind-up, flight, landing, settle, hold). An item written for a different action
then reads not applicable, with its reason, in the report. A shot never skips the check because no band exists for its
action; one skipped check would have flagged three real faults the moment it was finally run.

### REV11. Fix or declare every flag
stages: checks, self_review

A flag marks a place to look, not a value to hit. Each one is fixed at the nearest key, or declared with its reason and
the source of that reason. The review notes list every flag and what happened to it. A clean report is a diagnostic and
never stands in for looking at the shot.

### REV12. What the body check reads
stages: checks

Its input is the world-space joint geometry of each frame; channel values and scene comments are ignored. Anatomy items
cover the neck, spine, shoulder, elbow and knee (no hyperextension), wrist, hip and ankle range including sideways roll,
plus the floor, a hand sinking into the torso and a prop passing through a hand. Gaze items hold the head's heading in world space to
roughly 3 deg either side of the travel direction during locomotion, with small pitch and roll.

Locomotion items read the side-to-side travel of the pelvis and centre of mass, the vertical bob, the pelvis turning and dropping,
the shoulders twisting against the hips, how far the arms swing and how they time against the same-side leg, knee angles at contact,
loading and swing, toe clearance, step length and left-right symmetry. Contact items read planted-foot slide, balance at
each toe-off, the centre of mass over the support on a held pose with any carried load counted, no airborne frame in a
walk, and the arms under a load. From the spline pass on, curve items read angle jerk, position pops, keys on adjacent
frames, jitter and arc reversals. The questions it prints for the eye are answered in the self-critique.

### REV13. Real-human bands unless a style is declared
stages: checks, self_review

The default bands come from gait and clinical studies of real people. A chosen style may deliberately ask for more,
for example a lower body through the down, a knee that loads to about 53 deg (roughly three times the 15 to 20 deg of
real walking), or hips that twist about 10 deg at the contact. Such a larger amount holds only inside that style and is
declared with its source; everywhere else the real band applies. A note from the person who signs off outranks both.
The check prints the stylised band next to the clinical one so the choice stays visible.

### REV14. Joints stay inside human ranges
stages: checks

Typical limits on a realistic rig: knee 0 to 160 deg (150 as a stricter limit), and seen from the top a bent knee points
within 45 deg of its foot. Elbow 0 to 150. Hip flexion from 25 back to 125 forward, abduction from 30 in to 50 out.
The upper arm goes no more than 60 deg behind the side plane of the chest. Trunk twist stays under 40 deg (aim near 32),
bend from 30 back to 100 forward, and 45 to either side.

Bones keep their length within half a millimetre, and spine scaling stays between 0.90 and 1.05. A left and right pair
must not trade places in depth by over 15 cm between two frames unless an event is declared. A sharp trunk corner seen only from the
side (over 35 deg) or the top (over 60) that the front view and the 3D pose do not show is a flag.

### REV15. Contacts hold, and nothing sinks
stages: checks

A planted contact point creeps less than 1 cm per frame, measured over three frames. No point goes more than 1 cm below
the floor. Every foot target near the floor is reachable by the leg within 1 cm. A walk has at least one foot down on
every frame, no foot crosses the centre line by over 3 cm, and a touch-down never lasts a single frame. A
seated pelvis drifts less than 6 cm in total and less than 1.5 cm per frame. A planted foot turns no more than about 90
deg away from the pelvis heading (80 as a stricter limit).

### REV16. Balance is measured before a lift and on slow frames
stages: checks

Before a foot leaves the floor, the foot that stays carries at least 0.6 of the body weight. Whenever the body moves
less than 1.5 cm a frame, its centre of mass stays within about 3 cm of the base of support. A step meant to stay low
keeps the highest of heel, ball and toe under roughly 4.5 cm for a crouched body (pelvis at 0.45 m) and 12 cm standing,
with 1 cm of grace.

### REV17. Pops are sudden speed changes, outside declared hits
stages: checks, passes

A change of speed larger than 60 % of the local peak inside one frame is a pop, and so is trunk acceleration above about
8 g on a realistic body; a stricter guard keeps the trunk under 3 g. Contacts are exempt, and so are declared strike,
impact and smear windows: attacks judged good by eye were once flagged by this check. On any tracked path, a turn
sharper than 25 deg at speed is marked as a place to look.

### REV19. Smoothness is tested on the curve, not on the key count
stages: passes, checks

Every control curve and every derived joint curve reads as one clean line across and between keys: no zig-zag (the
second difference does not change sign on three frames running), no step in velocity, no notch, no stair and no flat
spot left by a solver. Keys on poses and breakdowns stay the default, since a sparse curve is simpler to keep clean and to
edit. Dense keys, even a key per frame, are fine as long as the line stays clean: for a fast action whose shape
changes every frame, a straight-ahead section, or an arc the poses cannot carry. Such a run is named on the exposure
sheet, and its review reads each of its frames, both on the control and on the joints it drives. Scan every rotation
curve too: a channel that stays flat across many poses has usually not been animated yet.

Still banned: frame-by-frame fixes that hunt a constraint or a check value until the curve turns noisy, a smoothing filter used to hide
noise, and a key added to hide a spike. A constraint is met by where keys sit and how their tangents run. If it cannot
be met that way, a key or a pose is wrong. Baking every frame at export is only a read-out.

### REV20. A designed stagger passes the strand test
stages: passes, checks

A deliberate shudder keyed on every frame is allowed when its channels and frames are declared. Split it into the
odd-frame strand and the even-frame strand. Each strand must read as a clean curve by itself, and the distance between
the two must open from about zero and close back to about zero. Any frame that belongs to neither strand counts as noise
and fails.

### REV21. Read the derived joints together near every contact
stages: passes, checks

Checking one joint lets the next one slip, and a key added to fix one part can make another pop. A knee pop at every
contact once passed on a jerk number. A foot snap at each push-off went unseen while only the knee was inspected. A
pelvis key meant to cure the knee then put a V into the contact; a pelvis lift one frame after contact can reverse the
pelvis in one frame, and a knee fix can drop the forefoot by a large angle at once. Close to a contact, foot pitch,
knee bend and hip height act as a single linked system.

After any change near a contact, and before keeping any fix, read the knee, the foot angle and the pelvis height
together, plus anything else the fix moves. Wherever two controls pass a job from one to the other, look for a spike or
snap in the toes, in the foot's tilt against the ground, and in how fast and how far sideways the ankle travels.

### REV22. Plot a travelling prop's speed against zero
stages: passes, checks

For any prop that travels, plot its distance per frame with a zero line. The sign never changes without a declared
cause. There is no dead creep: once the action is over, the prop does not keep drifting for many frames at almost no
speed. Each contact leaves the prop slower, in step with the lower bounce. A reversal that shows on this plot is usually already visible in the stepped
keys.

### REV23. A travelling textured ball spins the whole way
stages: passes, checks

A ball with a visible texture shows its rotation for the entire move: airborne, at every bounce and on into the
roll, and it only slows as the ball settles. Spin that appears only in the roll, or is too small to read on the pattern,
reads as no spin at all. A body with a tail is a different case and does not tumble. A working model: the spin stays constant through each
flight and changes only at a contact, where friction with the floor drags it about halfway toward the rolling value (speed over
radius); in the roll the angle equals the distance over the radius, easing to rest with the travel.

### REV25. Every check proves it can fail
stages: checks

Each check fails a synthetic shot built to contain its fault and passes a clean one. Each threshold carries a stated
physical reason and is never found by searching for a value that passes the tests. Add a noise test: a clean shape with
a few pixels of noise should still be read correctly in most trials (for example 53 of 60). Confirm the check does not
flag good reference frames everywhere. Work that has passed becomes a regression reference, and a regression stops the
build.

### REV26. A fault that slipped through becomes a check the same day
stages: checks, self_review

A gate miss is a fault that one gate catches although an earlier gate could already have seen it. When review catches something
the checks missed, reproduce it on the shot so the new check flags it, fix the shot, and confirm the check now passes
it. The new item lives in the tools with a test. No note should ever have to be given twice.

### REV27. Lessons from gate misses
stages: plan, blocking, checks, self_review

Most misses were already in the stepped keys or in the plan's own numbers. A passive decaying bounce on a creature, a
centre of mass behind the support on every step, a body rising into its contact, a two-frame jump out of a pushed pose
and a rock hidden in stepped travel keys were all readable early. Read the plan's numbers as possible faults, check
balance at every pass, and rerun the gravity check on any bump added in a later pass.

Other misses: two hops that were twins passed because no image showed the beat, so the beat is charted. A knee spike was
kept as acting, so acting never excuses a spike. A folded free foot, flared elbows under a box and an in-between handed in
as a key pose each fell to one plain question, so the self-critique asks them. A head frozen in the world, a load carried
high like a tray and a reference of the wrong body type all went unchecked, so each now has a check. A pass merged into a
generator with no stepped gate skipped review entirely, so every pass keeps its gate.

### REV28. The report card has four layers that are never added up
stages: checks, self_review, deliver

Gates are physical rules with a clear yes or no, and every one passes before the work is shown: volume conserved, no
part below the floor, the contact frame before the squash, and joints set going one per frame in order. Diagnostics are measured per principle, give a number and point at
where to look, but never grade. The eye checklist is answered by looking. The verdict of the person who signs off is the
only grade. Building the review refuses to finish when a gate fails or a passed reference regresses. A plain comparison
version gets a card but never a grade.

### REV29. Log every verdict beside its diagnostics
stages: self_review, deliver

Each verdict from the person who signs off is stored next to the diagnostics of the exact version judged. Over time
this shows which diagnostics predict what the eye sees. A diagnostic is weighted or dropped only from that evidence,
never by taste. Each shot also logs its first-pass verdict and how many notes it drew; the trend in notes per shot is
the measure of whether the self-checks work.

### REV30. The self-review takes the place of outside notes
stages: self_review

The target is first-pass quality with no outside notes, because a user of Kei will have nobody to give them. At each
pass gate, set every phase of the shot (the start, the loop, the stop, the settle and the idle, or each pose function)
beside measured values: real-world data when the style is realistic, and the style profile when it is not. Write the comparison as a table
of phase, reference value, measured value, verdict and fix. When a check is known to be broken for an action, read that
action by hand against reference values and declare the gap.

### REV31. Self-review before showing, on every pass
stages: passes, self_review, deliver

Before any pass is shown, run the checks fresh, clear every severe flag, run the measured principles, and fix or declare
each principle flag with its reason. Look at every frame in two views against the previous pass. Then answer honestly
whether this is good enough to show. A no means another pass, and the log keeps every answer. Step-by-step viewing finds
what checks only hint at (a prop flickering on the hit frame from channel interpolation, a sudden 56 deg elbow snap), and
each push can open a new fault, such as a hop, a collapse or a prop through the floor, so the gate repeats. After a
revision, set the parts the reviewer liked against the previous version with numbers, for example by overlaying the
old and new curves, and keep the old version renderable. A change there is undone or declared as a trade.

### REV32. Flip to the plain version to see the gain
stages: passes, self_review

Toggle between the pushed version and a plain version that is straight and evenly spaced. The pushed version has to look
obviously livelier. If the difference is hard to see, the push has not earned its place.

### REV33. A blind critic sees only pictures
stages: self_review

A separate critic compares two versions shown as A and B in random order, from images alone. It never sees shot data,
numbers or which version is which. Its scores are not shown anywhere until it agrees with the person who signs off on
most judged pairs; an early trial agreed on only one pair in five. Kei writes its own visual review before it sees any
critic score.

### REV34. Look at drawn feedback before acting on it
stages: self_review

When corrections arrive as strokes drawn on frames, render those strokes over the frames and look before changing
anything. Read the timing in them frame by frame, since a sequence of strokes often shows the rule before any words do.
The distance from the strokes is a diagnostic, never the goal. Notes and scores stay in the reviewer's own words. A test mark is not feedback.

### REV35. Report what was not checked
stages: deliver

Every report ends with what remains uncertain or untested. Questions of taste are written down as open questions for the
person who signs off, not settled silently.

### REV36. What only the eye can judge
stages: self_review, deliver

No check settles these: whether a pose reads and has appeal; whether a line of action is simple (fitting a curve to joints
misses the outline, the line of the back and the tilt of the head); whether the timing feels correct for the style when
played at full speed; whether
weight reads as heavy, light, floaty or limping; whether the motion has personality and fits the character. Nor these:
whether a contact is felt, whether the shot settles instead of ending sharply, whether overlap reads as one curve
following the force or falls apart late, whether a break of continuity that was declared is worth it, and whether a match to
the reference holds beat by beat at full size.

Which of two versions is better is also an eye question. Approval of blocking, of the poses, of how the timing feels
and of the final shot is a matter of taste and belongs to the person who signs off.

### REV37. Ask about exaggeration in both directions
stages: self_review

Ask an impartial viewer whether an exaggeration is too much and also whether it is too weak; asking only one way gets
the answer the question suggests. Check that a paused frame shows the emotion, and that a cheat toward the camera reads
from every camera the shot will be delivered through.

### REV38. Every pose function has a number and a look
stages: plan, checks, self_review

For each pose function in a shot (set-up, key, hold, wind-up, contact, passing, breakdown, settle and so on), name both
its measurable check and its eye-only check. The measurable column is a diagnostic, and many of its items are flags
only, never gates. The eye column is answered by looking and written in the self-critique.

### REV39. Parts differ in amount and timing, and none of them flickers
stages: passes, checks, self_review

Watch for two opposite faults: a figure that shifts as one rigid lump, every part travelling the same distance on the
same frames, and a figure whose small parts twitch and flick about. Each pass, confirm that distance and timing
vary from part to part and that no small part pops. A useful measure: for each key gap, compare how far the head, chest,
pelvis and wrists travel; when all four are nearly equal, the figure is stiff. Fix the large masses so they arrive and
hold firmly first, and only then open up the differences between parts.

### REV40. Compare a pass with its plan before showing it
stages: self_review

Before submission, compare the pass with its approved plan. Record the frames where the intended action is unclear, the mechanical checks that fail, and any unresolved author note. For each issue, identify the visible evidence and the proposed correction. Review again through the delivery camera after the correction.

### REV41. Review the motion as design
stages: self_review

Motion is a design problem too. Look for repeated shapes that vary, for balance with and without symmetry, and for
straight lines played against curved ones. When one version beats another, put the reason in writing: the line, shape
or contrast that made the difference. At the last review, check that each part belongs to the whole and carries the
idea, with nothing spare and nothing absent.

### REV42. Write a builder's brief for a literal reader
stages: brief, plan

A builder, whether an agent, a tool or a person, does exactly what the words say. In every brief or timing note, give
each beat as three things: what happens, how many frames, and the pose reached. For example, the head turns toward the
door over 6 frames, holds for 10, dips into a nod in 3 and comes back up in 5. Leave out idioms and metaphors, since a
literal reader performs them. Spell out each acting pose the shot depends on; without them the character just travels
flatly between two poses. One last read before sending turns any remaining figure of speech into a pose with a frame
count.
