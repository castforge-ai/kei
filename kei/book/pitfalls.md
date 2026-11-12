# Known pitfalls

kind: principle

Mistakes an animating agent has already made. Each rule names the mistake, how to spot it early, and what to do
instead.

### PIT1. Fix the size before the first pose
stages: plan, blocking

Scale changes every number in a shot. When a character is several times larger than its rig's usual size, a beat
lasts longer by roughly the square root of the scale factor (five times larger turns a 1 s beat into about 2 s), and
gravity measured in rig units shrinks by that factor. Resizing after blocking throws off the timing of every key. Record
the size, the weight class and the band of timings in the plan before posing anything.

### PIT3. Read the plan's own numbers as possible faults
stages: plan, self_review

A plan can print its own error, for example a step labelled long that is measured shorter than the short one, and the
blocking will then faithfully reproduce it. Every check may still pass. Before trusting the checks, read the plan's
figures against what they claim to be, then read the motion trail.

### PIT4. Look at the stepped poses before any spline
stages: blocking, self_review

Per-frame checks measure bodies, not story. A shot can pass every body check while its anticipation does not read and
several key poses look alike from the side. Lay the held poses out as sheets and read them from every view before
splining. Then judge each story pose in the camera the audience will see: the review views find faults, but the
delivery camera decides how far a pose must be pushed.

### PIT5. A pushed pose is only finished with its exit
stages: blocking, passes

Judging a strong pose on its own misses how the character leaves it. A pushed wince can hide a two-frame jump out of
it that shows only on the spline trail. Plan the way out of every pushed pose at the same time as the pose.

### PIT6. Overlap is designed delay, not simulation
stages: plan, blocking, passes

Springs, drag, momentum and constraints on a chain let every joint feel the driver on the same frame, which is not
overlap. Overlap is a timing choice, built joint by joint, each one a frame or so behind its parent. Simulation may
suggest how large a trailing motion is. It never sets its timing. Hands, claws or tentacle tips that take hold of something, stretch toward it or release
it are always keyed by hand: a simulated tip whips hard as each reach begins and again as it ends. A force model also tends to put a peak
late, for example the height of a wingbeat after the downstroke; key the lift and the sink on each stroke instead.

### PIT7. A falling chain feels no relative gravity
stages: understanding, blocking

A body and the tail attached to it fall together, so in free fall gravity does not bend the tail against the body.
What shapes the chain is air, the jolt of the impact, and the delay between its points; all points moving at once is
wrong. A per-segment clamp tends to inject zigzags and hooks at the tip, so avoid it.

### PIT8. Pin a follower, do not place it
stages: rig, blocking, checks

A tail on a free pivot can wind around a rotating body; pin it at one point, and keep a body that carries a tail from
spinning. Placing each segment straight onto a target lets the tip move by itself until the chain breaks apart. Judge
a follower against the path of its driver, never against its own tip trail, which hides the fault.

### PIT10. Check that the reference could have shown the detail
stages: references, study

Copying an absence from a reference is risky. A plain reference ball seems not to spin only because nothing on its
surface can show spin. A textured ball that travels keeps visibly turning for its entire journey, airborne
phases included, fast enough for its pattern to show the spin. Before copying something missing from a reference, ask whether the reference could
have shown it at all.

### PIT11. Compare a reference like for like
stages: references, checks, self_review

Small sheets, a strip of thumbnails, a single overlay or a single arc panel are not enough to judge a reference match.
Reading a stylised reference's camera wrongly can send several rounds in the wrong direction and produce false claims
that the arcs match. Claim a match only after a side-by-side look through one shared camera, beat after beat, frame
against frame, with the clip's frames and the shot's at full size in a single image. Track the hand path as well as
any prop tip. Pick a reference body that matches the target in build and sex rather than the one that happens to be
ready. Before toning a move down because it looks too big, measure what the reference actually does.

### PIT12. A reference matched frame by frame can still be impossible
stages: references, passes, checks

A tracker that lifts the feet can produce both feet off the ground at once, a high step while crouched, or feet
floating at full extension. Each frame matches the reference and the sequence still makes no physical sense. Read the
motion as a continuous body under gravity, not as a list of matching frames.

### PIT13. Do not assume what the brief did not say
stages: brief, plan

A choice carried forward by habit, such as a mirrored or left-handed character, can survive many rounds without anyone
having asked for it. Check every such choice against the brief, and keep the hand that holds a prop the same throughout.

### PIT14. Film rules need correcting for realistic game work
stages: brief, plan

Rules drawn from stylised film animation exaggerate on purpose. Applied unchanged to a realistic game shot, they read
wrong. For realistic work, scale the pushes, holds and squash down to what a real body does.

### PIT15. Every principle applies to every shot
stages: all

The order in which ideas were learned is not a limit on which ideas apply. A narrow reading lets staging, appeal,
exaggeration, secondary action and solid posing drop out of a walk or a lift, and faults such as a head
frozen in the world or a load carried high like a tray then pass. Run a pass over all the principles on every shot,
whatever its type.

### PIT16. Pose from how a real body works, not from habit
stages: blocking, passes

Animation habit puts relaxed arms forward with bent elbows. A relaxed standing arm hangs close to vertical, the elbow
bent around 15 deg, the hand beside the thigh. When a seated figure stands, neither foot leaves the floor before the body
has almost straightened, and the free arms drift forward, not back. A small box is held by its sides. Give every limb a job
and check it against a real body. When a correction note becomes a rule, test it against real bodies before it
hardens, or it can ban a correct pose.

### PIT19. Measure where a part points and how much it moves
stages: checks, self_review

Checks that ask only when a part moves can pass a walk whose pelvis swings about 13 cm side to side and whose head
turns with the hips. A normal gait moves the pelvis about 4 to 5 cm and turns it about 4 to 5 deg each way, while the
head keeps looking along the direction of travel. Measure world direction and amplitude for the pelvis and head.
Correcting the head must not freeze it in the world either.

### PIT21. Review the whole shot and every part
stages: passes, checks, self_review

Reviewing only the first bounce and the final stop misses breaks that sit in the late bounces and the settle; watch
the entire shot. After a note about one part, reading only that part lets the same fault through somewhere else. Where an IK solve
takes over from a foot roll, the toes can snap and the foot angle can peak in one frame at every toe-off. Wherever one
control gives way to another, inspect every part that depends on them, on each frame of that change.

### PIT23. Acting never excuses a spike
stages: passes, self_review

A one-frame buckle of a hurt knee is still a spike, even when the story says the leg is hurt. Even an extreme pose is
approached along an unbroken, smooth curve. Do not defend a break in the curve as acting.

### PIT25. Green checks are not a look
stages: checks, self_review, deliver

A shot can pass every check, the builder's own review and an outside glance while a pose shows flared elbows, a load
floating off the body or a breakdown standing in for a key pose. A combination of principles can pass every check with
a sharply hooked guard line. Checks are diagnostics. At the end of every pass, ask of each part in turn what is wrong
with it, and make sure a visual review actually ran before anything is approved.

### PIT26. A new kind of body gets its own check
stages: checks

When no existing check understands a body or a prop, such as a many-legged creature or a carried beam, build a
checker for it, with a test, inside the same shot. A missing band for a body is never a reason to skip checking it.

### PIT27. Calibrate on a pose that passes a pose test
stages: checks

Choosing a calibration frame by an extreme value goes wrong when the pose is unusual: in a kneeling or crawling pose
the lowest ankle belongs to a foot resting on its toes, not a flat one, and every foot reading then turns around. Pick calibration frames
that pass a pose test, such as an upright shin, the ball below the ankle and the ankle above the floor.

### PIT31. Solve on keys, not on every frame
stages: passes

Meeting a foot lock, a balance target or a reach with a correction on each consecutive frame fills the joints and the
interpolation with noise. Many keys close together are acceptable if the curve through them is clean; corrections on each frame
that hunt a target until the curve turns noisy are not. Solve on keys and breakdowns, read the target on the frames between, and let
the curve carry it. Running a smoothing filter over the channels is no cure either: it can shift a part by tens of
centimetres (up to about 39 cm) while hardly calming the pops. A per-frame search for a pose with more than one valid answer flips between answers on tiny input
changes, which looks like a spasm; time such a move as beats or solve it once per key pose.

### PIT34. Time a reaction from its measured cause
stages: plan, blocking

A reaction placed at a guessed frame can lead the event that causes it. Compute when the cause actually arrives, from
the geometry of whatever travels toward the character (a thrown ball, a wave, a falling branch, a sound), then add the
reaction delay.

### PIT35. Strapped things ride bones the animator keys
stages: rig, blocking

Anything strapped on, from a backpack to a tool bag on a shoulder strap or a child carried on the back, gets
whipped around when it is parented to a bone that a follow-through chain moves. Attach rigid things to a bone that is keyed by hand, such as the chest.

### PIT36. Leave room for the largest sweep
stages: plan, blocking

A wide part that sweeps below the body needs that much air beneath it, or its tips cut into the ground. For any
flapping wing, keep the body higher than half the span plus the reach of the downstroke. Near the ground, shorten the bottom of the stroke
instead of lowering the body into it.

### PIT37. The prop leads a shared load
stages: plan, blocking

When two bodies carry one prop, such as a table or a long board, key the prop first on one timeline, then key each body against it with a planned lag
for each reaction. Drive the hands by IK toward points locked to the prop; that keeps them on it. Shifting the load from the shoulder
to the hands, or back, needs roughly 6 frames.

### PIT38. Squash happens only at contact
stages: blocking, passes

Squashing a ball while it is still airborne, or on the frame it hits, are both wrong. The contact is its own drawing that just touches the
floor, stretched along the arrival path, and only a rigid ball stays round there. Typical early bounce errors: a ball
too big for its arcs, a stretch spread over five frames, the take-off drawing copied onto the contact, late bounces
squashing as hard as the first, a heavy ball stopping as fast as a rubber one, and a halving cushion spread so far
that the gaps reach zero.

### PIT39. Nothing eases into a gravity contact
stages: blocking, passes

A falling object does not slow down before the floor because it cannot know the floor is coming. Keep the spacing
wide right into a contact driven by gravity.

### PIT41. Answer a note from the cause, not with new motion
stages: passes, self_review

Fixing each new symptom in turn makes the result drift. When a note states a principle, build that principle first,
then look. When a note asks for more work on a moment, find the cause on the graphs and frames, and fix it from
something the object already has. A rock invented to enrich a settle, such as a ball rolling back on a flat floor,
answers the note with a new fault.

### PIT42. Contrast needs time to read
stages: plan, blocking

Strikes that arrive in about 3 frames, with dead holds between them, give no beat contrast and do not read. Give each
strike its anticipation and each hold a little life, so fast and slow parts contrast.

### PIT45. Phase errors are caught at the breakdown stage
stages: blocking, checks

Phase faults survive late when no stepped breakdown review exists and the reference comparison waits until polish.
Typical slips: arm extremes that land after the opposite foot strikes, when they belong with the peak of the opposite
thigh, roughly 4 frames ahead of that strike; a lean that peaks at the push instead of 1 to 2 frames after the strike; a side sway a quarter
stride early. Keep the breakdowns as a stepped review of their own, and compare phases with the reference there.

### PIT46. Measure a drawing before a rule rests on it
stages: references, study

A shape or number read from the wording near a drawing can contradict the drawing itself. Measure any shape or number taken from a drawing (fit the outline, count the tick rows, place the centres). Record where it came from and how it was measured.

### PIT47. Look at the data yourself before acting on it
stages: study, self_review

Acting on review data without rendering it, or reading a helper's summary of source material instead of the material,
lets errors through; an account error can be mistaken for a data error. Read every source in full. Check a long
machine transcript for loops and repeats. Read the review record before claiming that no notes exist. Make sure the
review images themselves are correct, since a strip whose cells do not clip can show hooks that are not in the motion.

### PIT48. A comment can silently remove keys
stages: blocking, checks

A note inserted partway along a line holding several keys can turn every key after it into comment text. The bake still runs
clean while keys vanish. Keep notes on lines of their own, never ahead of keys, and count the keys after each bake to
confirm none went missing.
