# Reading the brief and the character

kind: subject

Before Kei plans a move, it reads who will perform it. These rules cover the character evaluation (body measures,
mass, weight class, traits and the rig's controls), the checks a new rig gets, and the style study that follows
when the brief comes with style material.

### CHR1. Evaluate the character before anything is planned
stages: brief, rig, weight

No action analysis, beat chart or key exists until the shot folder holds a character sheet for this character. The
sheet records the body measures, the mass, the weight class, the traits, the rig's controls and a list of declared
deviations. The plan, the beat chart, the blocking and every check report refer back to it. A new character is
evaluated in full before its first shot. Where a part of the evaluation cannot be measured yet (an engine rig whose
controls no tool reads, for example), it is done by hand and the gap is written on the sheet.

### CHR2. Measure the body at rest
stages: rig, weight

Take every measure from the rest pose, in metres. Record the height; the leg length, taken as the hip height (for a
four-legged body, the mean of hip and shoulder height); the reach along the leg chain; the arm length from shoulder
to fingertip; the torso from hip to shoulder height. Derive the ratios of leg to height, arm to height, arm to leg and
torso to leg. Give the height of the centre of mass in metres and in leg lengths, and the support base as the spread
of the feet times the foot length (for a four-legged body, the box the paws enclose).

### CHR3. Weigh the character from its own volumes
stages: rig, weight

Compute the mass from the shapes the renderer actually draws, merged where they overlap and sampled on a grid of
about 1 cm, at the density of water (a living body is close to 1.0 to 1.06 times that). Give each sample to its
nearest shape, and each shape to the bone nearest its own centre, so an overlap counts once and a large belly is never
credited to the arms. The report gives the total mass, then each segment's mass, how much sits higher than the hips,
how much is in the limbs, and a belly index: how far the belly reaches in front of the pelvis, in leg lengths.

Stylised proportions distort this. A big cartoon head can hold a quarter of the measured mass where a real head holds
about 7 to 8 %, so read the segment shares before trusting what they imply.

### CHR4. Look at the silhouette sheet before trusting the numbers
stages: weight, understanding

Draw the character from the side, the front, three quarters and above, with each volume shaded by its mass (darker
is heavier). Mark the centre of mass with its plumb line, the hip line and the outline of the support, and add a
strip that shows the mass in each 5 cm slice of height. Then look at it. A viewer should guess the same weight class
from the drawing as from the measurements. When they disagree, one measurement is wrong: correct it before planning. For game work, also read the silhouette
through the game camera, not only in the four views.

### CHR5. Place the character in a weight class from load and leg size
stages: weight

Strength scales with the leg, so use the leg mass as the stand-in for strength. The load ratio is the body mass over
the leg mass. Correct it for size by multiplying with the leg length over 0.85 m: strength grows with the square of
size while mass grows with its cube, so a bigger body carries more load per unit of strength. On the corrected ratio,
light is below 2.5, average runs to 4.0, heavy runs to 6.0 and massive is anything above. Each step up carries about
one and a half times the load of the one below. A real adult with legs at about 32 % of body mass scores about 3.1,
inside average.

### CHR6. Say whether bulk or size made the character heavy
stages: weight, plan

The sheet names the driver of the category. Bulk means the uncorrected ratio already reaches it; size means only the
leg-length correction does. A heavy category reached through size keeps long, slow steps rather than short ones.
Weight and size stay separate dials: a brief may ask for a big body that moves light or a small one that moves heavy,
and that request overrides the measured category, declared on the sheet.

### CHR7. Record the scale, because size sets the timing
stages: weight, plan, blocking

Write the character's scale beside its weight class. Making a figure big does not make it heavy. What bigness changes
is duration: whatever gravity drives, from a drop to a swinging limb, a pendulum step or a slow sway, stretches in
time with the square root of the scale. For example, a crate that drops 0.5 m lands after about a third of a second,
some 8 frames at 24 fps; scale the same crate up a hundred times, to a 50 m drop, and the fall takes about 3.2
seconds, ten times as long. A giant therefore starts, stops and changes direction slowly because of its scale, and a
tiny creature does all three quickly. Weight is a second control, read in rebound, ground time, stopping and
absorption. Scale and weight are read separately and both go on the sheet. With nothing else in frame, motion alone
should reveal the size.

### CHR8. Start from the category's parameter table
stages: weight, plan, blocking

Each weight class comes with starting values for a walk, filled in for this rig in metres and frames. They are
starting points, judged by eye, not targets. These are Kei's starting values, to be calibrated on each rig with Kei's own tests. They are not population measurements or universal standards. Frame counts assume 24 fps; for 30 fps work, scale them up by 1.25. Step length is a
fraction of the plain step on this rig, which is itself about 0.85 to 0.97 of the leg reach. Vertical travel and foot
lift are fractions of the step length.

| Category | Step length | Frames per step | Contact to passing | Passing to contact | Down below contact | Up above contact | Foot lift peak | Anticipation share |
|---|---|---|---|---|---|---|---|---|
| light | about 1.0 (0.95 to 1.05) | 11 or 12 | 4 to 5 | 7 to 8 | 0.05 to 0.08 | 0.10 to 0.13 | 0.10 to 0.13 | 10 to 15 % |
| average | about 1.0 (0.95 to 1.05) | 12 or 13 | 5 to 6 | 6 to 7 | 0.085 to 0.105 | 0.075 to 0.095 | 0.08 to 0.10 | 15 to 20 % |
| heavy | 0.75 to 0.90; by size 1.00 to 1.15 | 14 or 15 | 8 to 10 | 5 to 6 | 0.12 to 0.16 | 0.04 to 0.06 | 0.04 to 0.06 | 25 to 30 % |
| massive | 0.60 to 0.80; by size 1.00 to 1.15 | 16 to 18 | 10 to 12 | 5 to 6 | 0.16 to 0.20 | 0.02 to 0.04 | 0.03 to 0.04 | 30 % and up |

Key frames inside one step, from contact at frame 0: light puts the down on 2, the passing on 5, the up on 8 and the
next contact on 12. Average uses 3, 6, 9 and 12. Heavy uses a down on 5, a catch on 7, the passing on 9, the up on 11
and the contact on 14; massive shifts these to 5, 8, 11, 13 and 16. A full cycle is two steps.

Side shift of the hips grows from about 5 % of the step for light, to about 10 % for average, to the centre of mass
over the support foot for heavy, with a waddle added for massive. Lean goes from slightly forward for light, to small
and upright at the down for average; a heavy belly leans back over the feet, other heavy bodies pull their poses down.
A stop takes no braking step and 4 to 6 frames for light, one step and 6 to 8 frames for average, two steps and 10 to
14 frames for heavy, two or three steps and 14 to 20 frames for massive. A heavy body takes about one and a half times
the timing of a light one, with a bigger anticipation.

### CHR9. Weight changes how far a part drags, not how late it is
stages: weight, passes

The delay of a dragging part is set by its distance from the driver, one joint per frame, and is the same in every
weight class: the belly trails by about 2 frames, the head by 3, a hand by 4. Weight changes the amplitude of the
drag and how long it takes to settle: about 2 extra frames of settle for light, 4 for average, 8 for heavy (more on
soft masses) and 12 for massive.

### CHR10. Heavy changes the amounts, never the confidence
stages: weight, blocking, self_review

The weight class scales the force of the push-off, the drop onto the contact, how deep and how long the down lasts,
how the mass carries and how far heavy parts drag. It never makes the walk timid: a heavy character still knows how to
walk, with the same confidence. The extra weight belongs in a firm push-off, a genuine drop into each contact, a deeper
and longer absorbing down, and belly, chest and arms riding through the step on lags of their own. Short, timid steps
with little foot lift read as tiptoeing over broken glass, not as mass. For a heavy body reached through bulk, step
length and foot lift may not drop below the bottom of the average band; below that floor the walk reads cautious
rather than heavy. Carrying something does not shrink the stride either; it stays within roughly 5 % of the stride
without the load.

Old age or frailty narrows the range of motion: reaches stay short, steps stay small, the feet shuffle. Slowness that
comes from great size is still sure-footed. Fear is its own trait, used only when declared.

### CHR11. A realistic heavy human walks wider, not lower
stages: understanding, weight, plan, blocking

At the same speed, measured heavy adults keep about the same step length and cadence as lighter ones. They widen the
step by about 30 %, keep both feet down longer, turn the toes out, hold the thighs apart, and stand slightly straighter
in every leg joint. No measurement shows them crouching more. Weight shows instead in the forces and when they happen:
how the mass lands at contact, how hard the push-off works, how the soft tissue drags and settles. Left to choose,
heavy walkers pick a slower pace, and at that pace both the step and the cadence drop. A carried pack on the back is
the exception and does deepen the knee bend under load. This finding is provisional.

The deep downs of the parameter table are a stylised read of weight: use them for stylised characters and creatures,
and declare which reading a shot uses. A stylised heavy walker may instead take a short stride and lift with both legs:
the two feet stay planted through the low and the drive, the legs raise the hips together, and only then does the free
foot leave, quick and low, to plant again soon. A normal walker sets the hips over the planted foot, lifts the other
foot at once, raises the body on the support leg alone and carries the free leg long through the air. The short
two-legged stride is a declared trait.

### CHR12. Write down what the character may not do
stages: brief, understanding, plan

When a character is old, frail, small or tired, its sheet carries a limits line: the largest reach, step and speed it
can manage. Age and fatigue narrow the range of motion; they do not take away intent. An action that needs more than
the limits allow is solved with small repeated moves inside them. Record how far the rig can move
mass around: whether it can arch the back, slope or lift the shoulders, and push mass up into the chest. A rig too
stiff for that is a limit stated before planning.

### CHR13. Name the traits that set the register
stages: brief, understanding, plan

Name a few traits, two or three, that make this character who it is, and the register that follows from them. A confident character, for
instance, moves slowly, shifts its weight over long spans and keeps its anticipations small. Record the reaction time
as a trait: the pause before a take or a reaction is short for a small or quick-witted character, about 5 frames at
24 fps or 6 at 30 fps, and grows for a large or slow-witted one. Set the caricature level from the role (straight, light or broad)
and note how the character sees itself. With a plain rig, identity comes from behaviour alone, so push those few traits
and keep the rest plain. Each trait points to the beat and the frames that show it; a trait with no beat gets one or
leaves the brief, and a trait that alters no pose has not been defined yet.

### CHR14. List the parts that act and the parts that move on their own
stages: understanding, plan

Make a table of the parts that can carry acting beyond the body: ears, a tail, the neck, hair, a coat, a hat, a prop
the character wears. For each, note its range of mood and how much it may change shape for animation. Add the
moving costume and props, plus each loose part that carries overlap, such as hair, straps, cloth or a tail. Flag which
loose parts the engine simulates, because any keys placed on them serve only as a preview. Record how much the design allows
the shape to change at all.

### CHR15. Plan acting around what the design lacks
stages: understanding, plan

Start with a table of stand-ins for every feature the design is missing: the absent part, the part that does its job
instead, and the gestures that then carry the meaning. An eyeless character, for example, looks with its head, so
each look on the sheet is a head turn toward a named target. For a creature, also note anything about it that viewers
may find off-putting, with how each item will be softened. Change only those items; the rest of the body and its motion
stay true to the species so it still reads as that animal. Then check the result with a viewer who has not seen it
before and who shares that aversion.

### CHR16. Size two characters side by side
stages: understanding, plan

When a shot holds a second character, the sheet names it and the two are designed and measured next to each other.
Their weights, sizes and registers are set relative to one another, not one at a time.

Each character present gets a present aim, the thing it is after at this moment, and a line on how it feels about each
other character there. A character with no goal is given one or taken out of the shot. That relation shapes every pose
toward the other: distance, facing, lean and the size of a reaction.

### CHR17. Plan in the character's proportions
stages: plan

Draw the thumbnails in the proportions of the character that will perform, not in the proportions of the person in
the reference. Carry the character's own design marks, such as a hairstyle or a distinctive shape, onto every figure,
even when the reference body is quite different.

### CHR18. Inventory every control of the rig before planning
stages: rig, understanding

Evaluating the character includes its rig. List each control with its name, type (forward kinematics, inverse
kinematics, pivot, space, master, proxy) and channels. List every custom attribute and switch: blends between inverse
and forward kinematics, which often live on the master, ground or root control instead of the limb; space and parent
switches; attributes for stretch, roll, pivot and curl; options to follow or to lock. List the rig's own tools for matching,
snapping, mirroring and resetting a pose, the proxies that have no channels, and the parent or sibling relation between
controls. This holds for an engine control rig too, before its first key. A root control that is a sibling of the body
control does not carry the body: key the root's travel and the body's travel separately, with the planted feet fixed
in the world. Probe the sign of every channel by keying it at frame 0, sampling the result and keying it back to zero.
A probe left behind by a crash poisons the next baseline, so after any crash compare the rest pose with the saved one
before keying again. Write it all into the character sheet as a controls table and a tools list, as the rig's facts,
and probe again on any other rig.

### CHR19. Use only what the inventory holds, and choose the limb mode per action
stages: rig, plan, blocking

Leave any control, attribute or tool missing from the inventory alone until it is added and its channels probed. From the
inventory, choose for each limb and each action whether it moves in inverse or forward kinematics: a planted or pushing
limb, or a hand on a prop, goes to inverse kinematics; a free swing or an arc goes to forward kinematics. Write each
choice and each switch frame on the plan, and make every switch with the match tool the inventory found.

### CHR20. Sweep each joint of a new rig before production
stages: rig, checks

A rig that is new or imported gets a range-of-motion clip before real shots: one joint after another rotates
through its full range. A joint that collapses, flips or pinches is a rig or model fault and returns there for a fix;
animation never covers for it. Volume
helpers at the pinch points stay driven by the rig. Write down where each control flips: a chest when the spine is horizontal, an elbow when the upper arm aligns with the
front of the chest, a knee when the ankle is directly ahead of or behind the hip, a planted foot that turns with the
pelvis. Fix these before a low crouch is posed. Record the rest pose of every rig involved, in particular how far
the arms sit below horizontal, so that a retarget compares like rest pose with like rest pose.

### CHR21. Key the rig, keep the game skeleton intact
stages: rig, deliver

Keys go on the rig's controls; the export is the skeleton the rig drives. Scene helpers such as a constraint to a
vehicle, a locator or a snap are fine only while nothing they add reaches the exported skeleton. Never change the hierarchy, the
bone list or the bone lengths of a game rig or skeleton to get a pose. Freedom to push a pose past a limit covers
amounts and poses, never the structure. Confirm the exported skeleton plays the clip exactly as the rig does:
compare bone positions frame by frame, and confirm the bone list and hierarchy equal the target skeleton.

### CHR23. Run a four-legged body on the scaled two-legged numbers
stages: weight, plan

For a four-legged character, scale the step numbers of the two-legged recipe to its leg length. Use its weight
category for timing, weight and overlap, scale a four-legged walk chart by that category, and plan the gait from
reference, declared on the sheet.

### CHR24. Study given style material before the plan
stages: brief, references, study, plan

When the brief arrives with a client set, a project folder of animations or other style material, study it before any
plan and write a style profile. Without any, write on the character sheet that no style input exists and the defaults
apply. Take inputs in this order: engine animation files, exchange files of motion, rendered clips, then the client's
written request. Map every clip onto one joint set so all of them are measured the same way. Measure each trait per
clip and across the set, at least: exaggeration against real joint ranges, squash and stretch, how far poses are
pushed, the register (realistic, stylised, cartoony; snappy or floaty), timing and spacing habits in frames, how much
parts drag and settle, how contacts carry mass, the way the character travels, what the arms and hands tend to do, and
how clean the curves are.

Watch the clips as well: a number with no look behind it is not a style reading. Write the profile as answered
questions and judge it in motion, not as percentages. Note for each principle whether the style uses it and how
strongly. If the style drops a principle entirely, that absence must be visible in the material. A choice that would
leave the motion lifeless goes to the person who signs off the shot. The profile sets the amounts; real-body values
fill in where it says nothing.

### CHR25. The style profile overrides the defaults only where it speaks
stages: study, plan, checks

Write the style profile beside the character sheet: for each trait a typical value with its spread and a few
example clips (two or three), then a list of departures, each naming where the project leaves real motion or the default amounts as a
declared style trait. Read the category's parameter table again against it. An amount the profile states replaces the
default for this project; a trait the profile does not cover keeps the default value. A joint pushed beyond its normal range needs a
matching trait measured in the material; anatomy and the eye still hold.

### CHR26. One register and one gravity per project
stages: study, plan

The profile states the register of motion, realistic or styled, and no character mixes the two. A single gravity
value and a single exaggeration level hold across the whole game, and the profile records the project's position on four points: bodies that
stay within human limits or go beyond them, motion that reads loose or weighty, how captured motion is handled, and
what exaggeration means in terms of movement. A keyed clip that plays among filmed or captured motion is toned down
until its register, tempo and stride match the set around it. Style comes from the client's set; motion comes from
life. Judge the profile only in motion.

### CHR29. Write the intent and the tone before any reference
stages: brief, understanding

Start the brief with two lines: the purpose of the shot and its tone. Only then gather reference or set keys. Next, tell
it as a tiny story naming the character, the place, the wish and the thing that goes wrong. Add the subtext under the action, such as sneaking out and then panicking, and the
texture of the timing in plain words, such as a bigger and faster reaction. Reference, poses and timing are then chosen
against these lines.

### CHR30. A touch between characters is its own beat
stages: plan, blocking

Give each contact between characters a line of its own on the exposure sheet, naming the one who reaches, the
softness, the frame where they meet and the frames of the response that follows. Tenderness approaches slowly and
slows further into the meeting; a quick approach looks like a blow. A first or unexpected touch earns a clear
response that begins after the contact frame, for example a flinch, a sudden stillness or a half step away. A
comforting touch lets the one receiving it relax under it. Fondness reads as a single small, unhurried gesture toward
the other, such as straightening a sleeve, with the head turned to them. In a game, a paired clip that includes a touch
names the meeting frame and slows the approach.

### CHR31. A lead character carries written movement rules
stages: brief, checks, self_review

A lead or a character who returns often gets a short list of movement rules, three to six, beside its weight class.
The list says how the character faces what it deals with, whether it ever gives ground, how it holds itself, and how
its hits land, for example: always takes the shortest line to its goal, never turns its back on a threat, keeps its
chin level, and lands every strike with its whole weight already committed. Every clip in the set is then scored
against the list in a yes or no table. Paused on the hit frame of each attack, the pose shows this character and could
not belong to another. A later version of the character, a redesign, or a character who ages or changes in the story
gets its list written again.
