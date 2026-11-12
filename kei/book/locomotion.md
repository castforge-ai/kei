# Locomotion

kind: subject

How a character travels on its feet: walks, runs, starts, stops and turns, the cycles they repeat in, and the measured
values of real gait that Kei poses from. Frame counts are at 24 fps unless a rule says otherwise.

### LOC1. Every gait is a controlled fall
stages: understanding, plan, blocking, checks

Walking, jogging and running all work the same way: after the high point the mass tips ahead of the foot that holds
it, and the next foot to land catches it. At a walk contact both legs are close to straight. The front leg reaches out
long to its heel, the rear leg trails well back with its heel up and its weight on the toes, and neither knee locks.
The body leans a little forward from the ankles, sits a little low, and the chest counters the hips.

Let the two legs set the stride; never solve the stride from a number or from the leg's reach and accept a contact
that reads bent. A stride found that way can leave both knees deeply bent and the front foot so far ahead of the mass
that the body would tip back once the rear foot lifts. Pose each contact as a fall that the front foot catches, check
the balance at toe-off and on every pass, and before a refining pass test every value borrowed from a table against
that balance: a passing height taken from a table can leave the centre of mass behind the support. A character whose
trait is bent knees, such as a sneak, writes that trait on the plan, and the fall still applies. A slow walk stays
close to balance; the lean grows with speed.

### LOC10. Use the phase map of a real walk
stages: understanding, blocking, checks

Each foot is on the ground for about 60 % of the cycle and in the air for about 40 %. There are two short double
supports, each about 10 to 12 % of the cycle, so the rear foot leaves about 2.5 to 3 frames after the front heel
lands in a 24-frame cycle. The support heel starts to rise at roughly a third of its own cycle. Older and heavier
walkers spend longer in double support. A run has no double support at all; it has two flights.

### LOC11. Pose walk joints inside real ranges
stages: blocking, checks

At a brisk walk the knee is almost straight at the heel strike (0 to 5 deg), bends 10 to 15 deg as it takes the load
(less in a calm walk), is near straight again in mid stance, about 40 deg at toe-off and 55 to 60 deg at its peak in
swing. The hip flexes 25 to 30 deg at contact and extends 10 to 20 deg just before toe-off. The ankle drops about 10
deg to foot flat in roughly 2.5 frames, flexes up about 10 deg late in stance and points about 20 deg at toe-off,
with the big toe bent up about 40 deg. The heel lands moving forward with almost no downward speed, so nothing stamps.
The visible foot lift happens early in the swing, heel up behind the folding knee, and then the foot skims low, about
1 cm, past the support foot.

### LOC12. The bob grows and the sway shrinks with speed
stages: plan, blocking, passes, checks

The centre of mass rises and falls more as a walk gets faster, from about 3 cm at 0.7 m/s to about 5 cm at 1.6 m/s,
while its side-to-side sway drops from about 7 cm to about 4 cm. It is highest over single support and lowest in
double support. The heel rise of the support foot keeps the bob small. Flattening the path by keeping the knees bent
gives a crouched glide, which costs effort and must be declared as a style; a head that holds level reads as gliding
with no weight.

Bob size tracks stride length and track width: short steps on a narrow track keep the bob small, and long steps on a
wide track enlarge it. When the step gets shorter in frames, shrink the vertical travel too; a quick walk with a slow
walk's bounce looks frantic.

A declared variant may scale the plain bob anywhere from zero to about three times. At zero the head travels level,
below the plain walk's low, on bent knees. At about two and a half times the down drops deep and the passing climbs
well above the contact. Toward three times the body tips forward, the step slows to about 16 frames and the free leg
kicks high and far.

### LOC32. Running is springing, not quick walking
stages: understanding, blocking, checks

In a run the foot leaves the ground earlier in the cycle the faster it goes: about 39 % at a jog, 36 % fast, about 22
% at an elite sprint. A jog cycle of 16 to 18 frames keeps each foot down for about 6 to 7 frames, with a flight after
each step. While loaded, the knee compresses to about 45 deg and only straightens to 20 to 25 deg of bend at toe-off.
The swing knee folds to about 90 deg, more in a sprint, against about 60 in a walk. The centre of mass is lowest in
mid stance and highest in flight, the reverse of a walk. Ground force peaks at two to three body weights, so a run
needs a visible absorb.

### LOC39. A realistic run at 5 m/s, as measured
stages: references, blocking, checks

One captured actor running at 5 m/s, read at 30 fps, gives these typical values for a realistic game run. A step
lasts about 9.4 frames and covers about 1.56 m, a cadence of about 3.2 per second. Stance 3 to 5 frames, flight 4 to 6
per step. The foot strikes nearly flat on the midfoot, heel up a few degrees, and leaves 27 to 42 deg heel up. Knee
about 40 to 48 deg at the strike, about 50 at its stance peak, 20 to 30 at toe-off and 125 to 140 in the swing, the
heel kicked toward the buttock.

The pelvis bobs 7 to 10 cm per step, lowest 1 to 2 frames after each strike and highest in flight, and moves about 4
cm side to side. The forward speed of the pelvis surges and brakes about 10 % each step. The trunk leans about 25 deg
on average and rocks 6 to 11 deg per step, with about 11 deg of side tilt toward the support. The head yaw stays within
a few degrees of the path, the head pitches down a little more than at rest, and the head bobs more than the pelvis
because the trunk pitch adds to it. These are one actor's numbers: trust the order of events, treat the amounts as
guides.

Sources: Epic Games, Game Animation Sample project (an Unreal Engine sample, 2024, distributed on Fab); frame-by-frame measurements of its motion-capture clips by Kei's maintainers, 2026-10-22. Measurements only, no assets; see THIRD_PARTY_NOTICES.md.

### LOC38. Jog and sprint are different gaits
stages: understanding, plan, blocking

A jog lands, absorbs and steadies its weight each step: a strike, a compression and an extension, more knee bend, a
hip and head bounce, loose arms and the biggest counter-swing. It reads unathletic or tired. A sprint is fluid again:
the head moves vertically even less than in a walk, the trunk is nearly locked, the twist is tight but never zero, and
the energy lives in the limbs.

### LOC34. Every run step has a declared flight
stages: plan, blocking, checks

Air time is what separates a run from a fast walk, and it is keyed to speed, growing in steps of about a sixth of the
step: about one sixth in the air at a jogging pace, about two sixths at a moderate running pace, and about three
sixths at a fast pace like the measured 5 m/s capture in LOC39 (4 to 6 flight frames in a step of about 9.4). At 30
fps keep at least one whole frame of flight per step. Step through one stride and count the frames with both feet
clear: a jog that hangs long floats, and a fast run with a single flight frame looks like a scramble.

### LOC18. A character walk starts from who walks and why
stages: brief, understanding, plan

Before any key, write the walker's size, proportions, personality, attitude and mood, what it wants, why it walks now,
and what the audience should feel. Body first, then personality, then mood, each visible without explanation. Moving
the feet in opposition only makes a walk move like a walk; it must also say who is walking. No two characters walk
alike, so never reuse a neutral walk unchanged, and when characters share a scene give each its own tempo, posture and
rhythm. Watch them side by side as silhouettes: each should be recognisable from its motion alone.

Study a real walker or a strong reference walk frame by frame and note one specific trait. Try the obvious version and
at least two others before choosing. Name the kind of walk in a word or two before keying, including whether it
travels on long strides or short steps, then carry a few strong traits through the whole cycle, ideally one memorable
one. A signature walk can be recognised as a silhouette at a distance.

### LOC20. The body scales the gait
stages: understanding, plan, blocking

A giant takes slow, long, heavy steps, almost in slow motion, and gets its speed from the stride. A small character
takes small quick steps, but each move still has a push, a muscle and a landing. An athlete rides on the toes with
more bounce; a nervous character walks faster. A larger body puts its feet further apart and shows less fluid
overlap. Stack proportions, mass, posture and nature, and let the proportions set the stride and the hip height.

### LOC22. Age, fatigue and emotion change the walk in known ways
stages: understanding, plan, blocking

An older walker cannot carry the rear thigh as far back (peak hip extension near 14 deg rather than 20), pushes off
weakly, tips the pelvis forward, widens the base and shortens the step, all without bending the knees deeply. Women,
once size is accounted for, tilt and twist the pelvis and the torso more and step on a narrower line. A tired walker
widens the base, sways more and steps less regularly, and need not be slower; a tired walk may droop and drag.

Emotion reads first from speed (roughly angry 1.8, happy 1.3, afraid 0.8, sad 0.7 m/s), then from one change of
posture. Sad: the head drops about 20 deg, arms hang almost straight, the swing and the bob shrink and the sway grows.
Happy: head a little up, bouncy, more arm swing. Angry: long fast strides, bent elbows, heavy contacts, a forward lean
with the chin out. Afraid: quick short steps on bent hips and knees, the upper arms held back. Proud: the body can sit
highest at the contact, an inverted bob that is declared.

### LOC23. Read anatomy signals and declare each one
stages: plan, blocking, self_review

Some walk features carry a meaning, so each one is written on the plan. When the pelvis drops a lot toward the
swinging leg, the walker looks poorly in control, like a toddler, someone hurt, exhausted or drunk. A pushed hip tilt
keeps the support side high, which is a different mechanic from a sag. A trunk that rocks over each foot in turn
makes a waddle. A big trunk bend over the support is a lurch. A trunk pitched well forward reads as an animal or a
sprint. Wide hips, a narrow single track, or heels give more pelvic twist and tilt; heels also keep the foot pointed,
the knees straight and the pelvis tipped forward. A front load deepens the lower back curve and leans the upper body
back. A toddler walks on a wide base with the arms held out for balance and no swing. A stiff ankle, a limp or a boot
is answered by the joints above it, more and more toward the pelvis and trunk.

### LOC24. A limp and an uneven walk need a reason and repeat
stages: plan, blocking

A limp spends less time on the hurt leg. That leg steps out long, then the good leg takes a shorter step, which gives
a long and short rhythm. A stiff ankle loses its roll, so the foot lands and leaves flat. A personality walk may give
its two steps different durations and lengths if the character has cause, such as 16 and 12 frames, and the difference
repeats every cycle. A shuffle alternates a long and a short body step, the long one taking about 70 percent of the
pair's time; it eases into its contacts and dips deeper in the long step than in the short one. A gait asymmetry that
is the character's flaw is declared so the checks read it as intended.

Acting never excuses a knee that snaps through a large angle in one frame. Spread a flinch or a buckle across two or
three frames and keep its curve smooth.

### LOC26. A sneak is chosen by intent
stages: brief, plan, blocking

A sneak may creep forward, back away, or rise onto the toes, and the brief names which one and how fast. The type
follows the intent, not a weight class: backing away suits a character driven by fear or up to mischief, rising onto
the toes suits a playful character that is sure of itself, and creeping forward is the default stalk.

In a forward sneak the body settles backward as the foot reaches out and still sits back when it touches down. Only
when the weight passes onto the new foot does the body travel forward, and the back foot keeps its contact until that
moment. The head lags. Ease the body and head, keep the feet even, put the longest cushion into the low passing, and
key the quick middle part closely along one smooth curve, with the arms balancing and the hands showing the intent. A
character approaching with a purpose does not stroll in: it moves slowly, stops and starts, comes in at an angle or
stays behind something, and each step tries to stay light.

Time a creeping sneak around twice the neutral step, 24 frames, and move a third of that either way for its speed: 16
for a hurried creep, 32 for a very careful one (30, 20 and 40 at 30 fps). A toe sneak stays near the neutral step, 12
frames give or take 2. A long-legged character can toe-sneak as fast as 5 to 6 frames a step, with a frame or two off
the ground and a twist of the pelvis.

### LOC36. Design every run before its first key
stages: brief, plan

Answer each question in writing: who is running, toward or away from what, and for what reason; what the head does
(a calm bob by default, or a side rock, or a small loop each step if the character calls for it); whether the legs
pump or push out broadly; the arm mode; what the belt line does; and whether the run favours flight or ground time.
Plan the stride, the forward speed and the bob as the three base numbers. If the legs are too short to cover the
distance, let the body travel further than the legs justify and cheat them, provided it looks smooth in the camera and
is declared. Then apply the walk levers at half size.

### LOC5. Timing and stride are two separate dials
stages: plan, passes

The same poses played faster or slower read as a different character. Lengthening the stride while keeping the speed
makes yet another character. A fast walk takes shorter, more frequent steps and keeps a little up and down for weight.
Decide both numbers on purpose and change one at a time.

### LOC4. Fix the step length in frames first
stages: brief, plan

Before posing, decide how many frames one step takes. The neutral reference is 12 frames at 24 fps (15 at 30), and
every other walk is planned as a multiple of it, counted in thirds, anywhere from two thirds to eight thirds: 8 to 32
frames, with 8, 12, 16, 20, 24 and 32 as the usual stops. Convert to 30 fps with a factor of 1.25. Pick the multiple
from how much drive the walker has: the less energy or purpose, the higher it goes, two being one step each second;
below one, the walk turns springy and close to a run. Fatigue can stretch a step to about twice its normal length. At
8 and 16 frames the quarter-step keys fall every 2 or 4 frames; at 12 they land on every third frame.

Real people take about two steps a second across a wide band of speeds, roughly 12 to 13 frames a step anywhere
between 0.8 and 1.8 m/s, and go faster mostly by lengthening the stride. Comfortable speed is about 1.3 to 1.5 m/s.
Above about 2 m/s a walk looks strained and the character should run. A walk that speeds up only by stepping quicker
with the same stride reads hurried.

### LOC33. Pick the run tempo from the figure and the attitude
stages: brief, plan, blocking

Choose the frames per step before any pose, as a whole number from 2 to 8 at 24 fps. For 30 fps, scale by 1.25 and
round to the nearest whole frame, alternating 7 and 8 where the result is 7.5. Start from half the neutral walk step,
6 frames, for an ordinary run, a jog or a heavy run. Go up toward 8 when the run needs room for big, loose shapes or a
pared-down cycle. A wild run whose shapes keep changing from step to step still works at about 5 frames. Below that,
the fewer the frames, the shorter the legs and the simpler and more repeated the poses must be; 3 is the fewest in
which the legs still read as turning over, and 2 is the floor. Long legs need 6 frames or more a step, or they smear
into a blur. A realistic game run sits between 8 and 6, about 9.4 frames a step at 30 fps (LOC39); a stylised hero run
nearer 6.

As whole cycles at 30 fps, about 10 frames reads as a dash, 15 as a run and 20 as a leisurely run; past about 16
frames at 24 a run loses its urgency. Note the step at both frame rates on the plan.

The tempo carries the attitude. Near four steps a second a run reads eager and aggressive, while sprint poses at fewer
than about three steps a second seem to float. A character on its way into a fight can show controlled power at about
8 frames a step at 30 fps, a touch slower than the eager pace.

### LOC29. A walk to a goal changes its steps with the thought
stages: plan, blocking

When a walk is not a loop, set each step's frame count from what the character is thinking at that moment: steps get
quicker once attention locks onto the goal, and slow again as the body starts to prepare what it will do there. Close
to the goal the strides get shorter and the key poses crowd together. Never hold one stride length from start to
finish; only loops keep their steps even.

### LOC30. Ground changes the walk
stages: plan, blocking

Climbing stairs, the leading foot sets down flat while the back foot hangs on a moment; descending, each landing
absorbs more deeply. On a slope a run leans further forward and pumps the arms harder going up; going down it leans
back to avoid tripping. The amount grows with the angle, and the slope version keeps the same step phase as the level
one. In deep, soft ground such as snow, a stride can stretch to four times the neutral step, about 48 frames, with the
knee lifted close to horizontal.

### LOC31. Shoot or pick walk reference for what it shows
stages: references, study

For a neutral walk use a neutral walker. Read stride and heights from the side, and hips, chest and arm opposition
from the front or back. Read the bob on one fixed point, the top of the head or the hips. Note the push-off, the
weight shift, the stride and the key frames, and keep the footage open through every pass. Work from all angles and
deliver the views the brief asks for.

### LOC2. Block the hips first, as a bouncing ball
stages: blocking, checks

A walk is the whole body, but its engine is the pelvis, and the pelvis moves like a ball. Pose the hips alone first,
legs hidden, then hang the legs from them. Space them like a ball too: they linger near the top and drop fast into
the down. In every review of a walk, judge the hips before anything else. Still hips fail the walk.

### LOC9. Block a walk from the body outward
stages: blocking

Work in this order. First the body alone, limbs hidden: its path, its bounce, its step rhythm, and its leans if the
shot starts or stops. Then the contact and the crossing on every step, accepting foot slide for now and judging pose
and rhythm. Then the down, two or so frames past each contact, with the front foot flat and the back heel lifting, and
the up, two or so frames past each crossing; lock the planted foot from the down. Then the in-betweens, the hip twist
keyed with the main poses, the shoulders as the inverse of the hip twist, the arms in rotation from the shoulder down
with each joint a little later, and the head last. Check the footprints against a centre line from the front.

### LOC3. The plain walk keys on quarters of a twelve-frame step
stages: plan, blocking

The neutral starting walk takes about one second per cycle: 12 frames per step at 24 fps, 15 at 30. Within each step
the contact sits at 0, the down at 3, the passing at 6, the up at 9 and the next contact at 12. Keep both steps equal
at 30 fps by putting the passing on frame 7 or 8 as needed. This is a starting point that is changed on purpose to
suit the character, never a law.

A two-step cycle puts its first contact on frame 0 and repeats that pose, moved on by one cycle of travel, on frame
24. Play and export frames 0 to 23 so the joining pose shows once. Give each step exactly 12 frames: keys placed on 1,
12 and 24 leave one step a frame short, and the loop pops.

### LOC6. The body is lowest after the contact and highest after the passing
stages: plan, blocking, checks

The height order of a plain walk is down, then contact, then passing, then up, from lowest to highest. The low point
comes just after the contact and the high point just after the passing, never on it. As ratios of the step length a
typical walk sits about 0.1 below the contact at the down, about 0.02 above it at the passing and about 0.09 above it
at the up. Each pose type gets the same height on every step; read it on the curve. The passing is never low because
the support leg is vertical there. A personality walk may change this order, and says so on the plan: the low can move
onto the contact with a shallower dip in mid-step, the step can dip twice (near frames 3 and 9 of a 12-frame step), or
the body can peak on the passing.

### LOC25. A variant walk moves one lever of the plain walk
stages: plan, blocking

Start a variant from the plain walk with one lever moved and the rest left plain; move more than one lever only when
the plan declares the combination. The levers are the size of the bob (LOC12), the resistance of the ground (LOC30),
and where the low and the high fall in the step (LOC6): the low on the contact with a shallower dip in mid-step, two
dips per 12-frame step near frames 3 and 9, or a peak on the passing. Write each lever moved and its value on the
plan.

### LOC63. The hips travel forward evenly
stages: blocking, passes, checks

Start the forward travel of the hips as a straight, even ramp, then shape it. Push the down a little ahead, so that
by the moment the rear foot leaves, the pelvis is already above the leading foot. As typical fractions of the step from the contact:
about 0.2 at the down, about 0.42 at the passing and about 0.63 at the up. On screen the travel must look even: a
stall after the contact followed by a jump is fixed at the key that causes it. A walk always keeps one foot down, and
its root moves at an almost steady speed that quickens slightly at each push; a big surge or a stall reads as a limp.

### LOC8. The weight moves over the supporting foot
stages: blocking, passes, checks

The hips drift toward the supporting leg in one smooth wave per cycle, with no flat holds, peaking between the
passing and the up at about 0.1 of the step. At the contact the hips still lean toward the side the weight comes
from; at the down they head toward the side it goes to. The feet land a little in toward the centre line. A heavy
walker shifts more, until the whole hip mass crosses the line. A run shifts less than a walk.

The tilt and the side shift together can pull the support foot out of reach at the passing and the up. If they do,
lower the whole body a little rather than give up the height order. A sideways shift of the hips always brings its
tilt along with it; a hip that slides across while staying level looks mechanical. When one view has been approved and another must
change, keep the approved values in absolute units, so a longer stride does not quietly change the front view.

### LOC7. The hips twist, tilt and pitch on every step
stages: blocking, passes

The pelvis is one object with three rotations. It twists about 10 deg at each contact, the side of the leading leg
forward, the sign flipping each step. On the passing it tilts by about 4 deg, its raised side above the standing leg
and its low side over the leg in the air; the tilt holds through the up and returns to zero at contact and down.
About 7 deg already reads too much in a plain walk. Its pitch is the overlap of the up and down: build it by eye, push
it, then scale the whole curve down, and never let it peak on the same frame as the height. The tilt is invisible from
the side, so key it and judge it from the front.

Two mechanics can lift a hip. Either the free side rises first and carries its leg up, or the leg that has just landed
pushes its own side up. Choose one for the walk and keep it on every step; the plain walk uses the second, and a still
pose keeps its support side high. Seen on screen, typical tilt sizes are 0 to 4 deg for a realistic or plain walk,
about 11 to 12 deg with added twist for a pushed or feminine walk, 11 to 18 deg with a large twist and a wide stance
for a cartoon walk, and 19 to 20 deg when a load forces it. A cartoon walk is a real walk pushed further, never motion
with no real cause, and a shot keeps one push level.

From the side, the pitch takes one set of values for every step. A typical set: tipped back about 3 deg at the
contact, further back at the down (about 4.5 to 5.5), forward about 3.4 at the passing, and the up close to the
passing. Check the forward travel again after changing the pitch.

The shoulders twist against the hips, the arm going back taking its shoulder back. The twist is largest at the
contact, with both lines near level from the front; the tilt and the trunk squeeze are largest at the crossing, where
the twist is least. Once refined, the trunk follows the hips by one to three frames in both its turn and its squeeze. Hips and
shoulders turning as one block read wrong unless the character calls for it. A faster gait tightens the twist and
never removes it. In every walk the shoulder line tilts against the belt line, and which side of the pelvis is low at
the passing is a declared choice: the plain walk lets the swing side hang a little low, while a belt hiked on the
lifted side or a level passing is a style.

For a personality walk, push the twist and the tilt until they read in the camera, and the hips may sit ahead of or
behind the chest and feet for the whole walk. Key the twist with the contacts and passings as they are posed, then
re-solve the legs; adding it later changes every leg pose. Check the feet again after it.

### LOC62. Keep the hips simple, and settle them first
stages: blocking, passes, self_review

Settle the pelvis turn and side tilt, and get them reviewed, before refining the trunk or the feet. Judge them from
the front, back, top or a three-quarter angle: the two hip joints take turns swinging fore and aft and rising and
falling, which a side view cannot show. A person walking moves the hips plainly, without over-turning them. Keep a
single angle for a whole phrase and save the change for the one moment that matters. Animate only the channel that
tells the idea. If the feet are doing intricate work, let the hips sit on a few steady angles with no bob: clarity
wins over activity.

### LOC16. The trunk leans a little and the head stays on the path
stages: blocking, passes, checks

Overall the trunk tips forward about 6 deg, rising to about 13 at speed, and a little more at the contact than at mid
stance. During single support it leans sideways a few degrees over the standing leg. The head is held steady in space:
it keeps facing along the path, and it pitches against its own bob, the nose rising a little at the down and dropping
a little at the up. A walker looks forward; a head that turns left and right on each step, or a pelvis that swings
wide from side to side, is a fault unless the character has a reason. The head is never locked either.

Each sideways hip tilt gets a spine tilt the opposite way on the same key, so the trunk bends a little toward the
support as an active balance. A large trunk lurch is a declared sign of weakness or a toddler. Seen from the side with
the travel removed, the head and chest rise and sink on an almost vertical stroke; a circle or a figure eight there
reads as an odd, nodding gait and is used only when declared.

### LOC14. Write head travel, track and step as one set
stages: plan, blocking

Decide the head's vertical travel, the track width and the step length together, using the relations in LOC12, and
write them on the plan as one set. Declare a level head when it is chosen. Test the set by watching the head alone:
the walker should be recognisable from its rise and fall.

### LOC37. The order of a run step, and the pose that leads it
stages: blocking

A run step goes contact, down, push-off, flight, passing. The contact lands on the ball and goes flat almost at once;
the down follows 1 frame later at 24 fps (1 to 2 at 30); the push-off makes one long line from the rear toe to the
head; the passing is compact with the heel kicked up. At contact the body tips into the direction of travel with the
head in front, the hips toward the front foot and the shoulders countered. The contact leg is bent in a realistic
run; a straight reach is a declared choice of a broad run.

Contact first is the default plan, not the only one. Any pose family can be the run's extreme. A stretched push-off
sells power, an open flight sells joy, a low down sells weight. Pick the one that sells the idea and let the others
become the breakdowns.

### LOC35. Walk devices carry into the run at about half size
stages: blocking, passes

Every device of a walk has a run version: the bob, the side sway, the fore and aft travel, the opposite bend and twist
of body parts, the loose feet. A run step lasts about half as many frames as a walk step, so give each device about
half its walk size, measured against the character's own walk where it has one. Twists and tilts kept at full walk
size make a run rubbery. The body curve reverses each step through a straight passing, the shoulders work against the
hips, and the run shifts its weight sideways less than the walk does.

### LOC44. The run bob grows with the stride and sinks before a jump
stages: plan, blocking

Longer strides bring a larger bob. Per step the pelvis rises about a third to a half of the character's own head
height, never a whole head; on adult proportions that is about 8 to 12 percent of leg length, some 8 to 11 cm (the
measured run in LOC39 gives 7 to 10 cm). A larger bob is a broad cartoon value. As a running jump approaches, each of
the last contacts sits lower than the one before, rather than holding cycle height and crouching suddenly.

A declared heavy or cartoon-heavy runner reverses the usual shape: it falls into the down right after the top, then
spends most of the step climbing, about one frame down for five up, with the head pushed forward to help the rise and
a short flight. It still runs with confidence, never with care. A real heavy body runs more upright on a longer
stance, so this split is a style amount.

### LOC43. A broad run's body rises, hangs and drops
stages: blocking, passes

In a broad cartoon run of about 6 frames a step, the root falls over roughly 2 frames, climbs over 2, then hangs for 2
at the top, shaped by tangents rather than by moving keys. The body pitch lags the height: it is still tipping down
while the body rises and follows up after the top. The forward travel of a steady run is one even curve keyed only at
its ends. Find the legs straight ahead, with the body fully airborne the frame before each contact, then reduce them
to their key poses. These values belong to the broad style; a realistic run keeps the measured ones.

### LOC41. Sideways trunk motion is built step by step
stages: blocking, passes, checks

In a run, and in any gait with a short stance, every sideways channel of the trunk (body tilt, spine side bend, hip
drop) belongs to one step. Each pulse begins when its foot strikes, is largest one or two frames later at that step's
down, and dies away during the following flight; the next step makes its own pulse toward its own side. One slow wave
across the whole stride reads as a rock every two steps and looks wrong. For a cruising run, a lean from pelvis to
neck of about 9 deg reads controlled; about 13 deg starts to look tipped.

### LOC40. Run arms stay bent and stay smaller than the legs
stages: plan, blocking, passes

In a fast realistic run the elbow stays closed, about 100 deg on average and never under about 75. The upper arm
swings close to 90 to 100 deg in the world, each arm opposite its own leg, the hands ranging from just behind the
pelvis to about 40 cm ahead of it. The arm extremes land within one or two frames of the opposite leg's extremes, and
the arms never roll backward.

The arm behaviour is a character choice named in the run brief, set by two settings. Its timing against the legs: in
counter with them as in a walk, at twice or half their rate (LOC27), or not swinging at all. Its shape and path: the
plain fore-and-aft swing, bent and fixed, across the body, thrown forward, or loose and flailing. Reduce the arm swing
as steps get quicker, keeping the legs as the first thing the eye reads; on a very fast run too much arm is the common
fault. Double-rate arms are smaller and declared.

A hero run swings larger than a realistic jog. The forward fist rises near chin height close to the midline with the
elbow near 90 deg, the back elbow lifts to about shoulder height behind the trunk, and the hand travels about half the
figure's height. The arms peak on the push-off and in the flight, never at the contact. Arms held tight to the body
are one reason a run looks plain.

Sources: Epic Games, Game Animation Sample project (an Unreal Engine sample, 2024, distributed on Fab); frame-by-frame measurements of its motion-capture clips by Kei's maintainers, 2026-10-22. Measurements only, no assets; see THIRD_PARTY_NOTICES.md.

### LOC27. Arms may run at half or double the legs
stages: plan, passes

A stylised walk or run may swing the arms once for every two leg cycles, or twice per leg cycle, with the arm extremes
landing on leg keys. Declare it. Arms at double rate swing smaller; arms at half rate have time for a large arc. A
loop that carries half-speed arms must be two leg cycles long. Keep the arm timing close enough to the legs that the
result still reads as a walk.

### LOC42. A fast run never repeats a silhouette
stages: blocking, passes

Pose the second step of a run as a copy of the first, then make them differ: one higher or lower, a different back
curve, a twisted foot, different arm and leg shapes. Speed raises how much the paired steps should diverge, so the eye
does not see one leg and one arm going round. A jog may keep its counters closer, never identical. Keep the step
timing even while the paired poses vary.

### LOC17. A plain walk is consistent; personality only on purpose
stages: blocking, passes, self_review

A neutral walk is even by design. Mirror the values from step to step with the sign flipped, keep the two steps
within a small band, and read each channel as a curve per pose type. Nothing should vary so much that a viewer sees a
limp or a mood. Any curve that does something unplanned is either adopted on purpose and written down, or removed.
Real walks are slightly uneven, so a character walk may let its second step differ.

### LOC19. Keep the mechanics in the contacts; put the character in the breakdowns
stages: blocking, passes

Start a character walk from the neutral recipe. Keep the contacts and the passings as the mechanics, and place the
personality first in the breakdowns, for example a kick, a double motion, or a breakdown set higher or lower. Hold one
attitude pose through every key, give the feet one behaviour on every step, and point them on purpose. A trait on one
limb shows on every pose of that limb. Retime last, by changing hold lengths, and only in the section that must feel
different. Play contacts and passings alone, stepped: the character should already read.

A passing may also change the body's shape rather than its height, stretching or squashing on a level pelvis with the
volume kept. Hold it long enough to register, let one limb arrive late so the figure balances over it, and declare it
on the plan.

### LOC57. Rough a travelling walk first, then make the cycle
stages: blocking, passes

A walk worked out only in place tends to look mechanical. Rough the walk travelling over the ground first, then turn
it into a cycle that keeps some variation and still closes. Games need loops; the loop is made from a walk that
already lives.

### LOC28. A stiff or popping walk still needs life
stages: passes, self_review

A bouncy walk can sit highest on the contact and stay down through the passing, and a walk can rise and drop in sharp,
clipped steps. That stiffness can charm, yet if nothing stretches, overlaps or lags, the figure turns flat and
puppet-like. Keep something moving on every frame: a drag, a settle or a moving hold. Soft masses counter the body:
they lag past the passing, cloth later, hair last.

### LOC47. A start from rest begins with the hips
stages: blocking, passes

From a still stance the pelvis moves first: a small sink and a shift over the foot that stays. Next the trunk
rotates, leans or coils, and after it the chest, shoulder, arm and hand follow, each one at least a frame behind the part before it. If the hand or
the head sets off while the hips wait, the body looks dragged on a string. When the cause is a look or a thought, the
eyes and head may move first, but the hips still lead the body.

Before each step the hips travel over the foot that stays down; that shift is the step's anticipation and grows with
the size of the step to come. The first sink of a start from rest goes lower than any down in the cycle that follows.

### LOC46. Starts and stops lean; steady travel stands nearly upright
stages: plan, blocking

Locomotion from rest goes through five body lines: upright, a forward lean to start, nearly upright at speed (a run
keeps a small steady lean, about 10 to 15 deg), a lean back to stop so the feet can brake, then upright again. Harder
acceleration or harder braking means a bigger lean. A heavy body leans only a little to start but keeps the lean for
longer. The more the body leans, the quicker the feet must swing through. A sprint start plants its first foot late
under a body already falling. An explosive start leaps directly into a broad, low contact pitched forward. In a stop,
the backward lean is only a comparison: the feet move out in front and do the braking, and the trunk rarely tips
behind vertical.

In a game, starts, stops and 180 deg turns stay as short as their read allows, and each can be cut into by the others.
A 180 deg turn shows the feet planting and the weight moving across. Test by flicking the input back and forth fast:
the character must shift precisely, never travel several metres on a short nudge. Surface variants, such as ice, stay
as consistent and as readable as the base set.

### LOC48. A run start dives, and the lean leads the speed
stages: references, blocking

A measured realistic run start at 30 fps holds still for a few frames, then everything begins together: the trunk
begins to tip forward, the pelvis sinks a little and eases back, the centre of mass heads forward. The trunk lean
climbs to about 60 deg by about frame 15 and returns to the run's 25 deg by about frame 36. That lean is the first
large motion, and it is ahead of the speed by roughly 10 frames. The pelvis sinks 15 to 20 cm and then rises into the
run over about a second. Root speed climbs nearly linearly to 5 m/s over roughly 24 frames, half speed by frame 12.

The first step is a short set step under the diving body, then two strides reach full length. The arms begin by
flinging backward with the elbow almost straight, and the elbow closes on the first forward swing. The anticipation
is the dive itself. For a player-driven start the still frames are dropped and these values guide the upper end of
the speed ramp.

Sources: Epic Games, Game Animation Sample project (an Unreal Engine sample, 2024, distributed on Fab); frame-by-frame measurements of its motion-capture clips by Kei's maintainers, 2026-10-22. Measurements only, no assets; see THIRD_PARTY_NOTICES.md.

### LOC49. A walking stop is decided a step early
stages: plan, blocking

The final push-off is weak and leaves the rear leg trailing. The final landing leg reaches further forward, straighter,
and brakes harder, and the body may rise onto the front toes. If momentum still takes the mass beyond the front foot,
one more step is needed. A planned stop slows across its final two or three steps. A young adult walking at about 1.3 m/s halts
in about 463 ms, and an older adult at about 1.2 m/s in about 574 ms (unchecked); at 24 fps that is about 11 and 14 frames, a
conversion. Older men take two steps to stop far more often than young men: 46 % of trials against 20 %.

Sources: Jaeger RJ, Vanitchatchavan P (1992), Ground reaction forces during termination of human gait, Journal of Biomechanics 25(10):1233-1236, doi:10.1016/0021-9290(92)90080-K. Tirosh O, Sparrow WA (2005), Age and walking speed effects on muscle recruitment in gait termination, Gait and Posture 21(3):279-288, doi:10.1016/j.gaitpost.2004.03.002.

### LOC50. A run stop brakes, overshoots and squares up
stages: references, blocking, passes

A measured game run stop at 30 fps goes from 5 m/s to rest in about 10 frames with one braking step, the foot about
0.6 m ahead of the centre of mass and on the ground for about 9 frames. The pelvis sinks by roughly 22 cm. The other
foot comes down behind and remains there, and a small squaring step of about 0.2 m brings the feet into the standing
stance. At the moment of hardest braking the trunk straightens by about 9 deg, folds a little into the absorb, then
rises. The elbows open sharply within a few frames of the brake.

The pelvis passes its final place, about 17 cm on that capture, and comes back. Height arrives first and bounces while
the body still travels, then the head nods about 12 frames after the pelvis low and rises past its rest value, then the
limbs settle. A full realistic settle takes about 3 s, each part with its own late tail; nothing simply hits the
final pose and dies, and no frame lands every part at once. A game stop covers little ground but plays its reaction
for a long time. Film work may use several braking steps instead.

In a game, the root of a player stop halts within a short, fixed distance and the body plays its reaction after the
root is still. The left-foot and right-foot stops cover the same root distance in the same playable length, and both
finish on the one idle pose through the squaring step, never by mirroring the idle or the clip.

Sources: Epic Games, Game Animation Sample project (an Unreal Engine sample, 2024, distributed on Fab); frame-by-frame measurements of its motion-capture clips by Kei's maintainers, 2026-10-22. Measurements only, no assets; see THIRD_PARTY_NOTICES.md.

### LOC51. A step is the last resort
stages: plan, blocking

People do not step unless they must. When leaning or stopping, the body first travels well out over its base. After a
landing that still carries momentum, small late steps catch a body that keeps falling forward; they are never a walk.
An off-balance recovery is planned as its steps: the lean, a foot thrown out, a step backward, the catch, the weight
settling, and a final small half step, never a dead stop.

### LOC53. A turn moves the mass first, leads with the head and pivots at the pelvis
stages: plan, blocking, passes, checks

Plan the path of the centre of mass first: it starts drifting toward the new heading before anything else, through a
foot placed outside the line or a trunk tilted inward. Then come the eyes, the head, the chest, the pelvis, and the
feet last. Turning from a stand toward a target, the head trails the eyes by 2 or 3 frames, the chest trails the head
by another 2 or 3, and the first foot moves roughly 12 frames after the head begins, the feet then coming around in
short steps. Turning while walking, the head turns into the curve about 5 frames ahead of the chest on a gentle curve
and as much as 24 frames ahead before a sharp corner. Lean the body about the pelvis with the feet placed outward; a
body that tilts from its feet topples like a skittle. Free arms are a result of the trunk: they lag, swing outward as
the body turns, carry beyond and come to rest at the end.

A turn toward the front foot's side spins on that foot; a turn the other way is a wider, steadier stepping turn. A
confident young body turns the head, then the chest, then the hips; a frightened, frail or fragile character rotates
as a single block. If every part starts on the same frame, or the pelvis leads, the turn looks mechanical.

### LOC60. Size sets a quadruped's stride time
stages: plan, blocking

Set the stride period from the animal's size first: roughly 1 to 1.5 s for the largest land animals, around 3 m at the
shoulder; about 1 s for an animal around 1.6 m at the shoulder; half a second or less for one around 25 cm at the
shoulder. Then build the character from how it carries itself (how high the head rides relative to the shoulders, how
low it crouches) and from how high it lifts its legs. With the timing left unchanged, carriage and leg lift alone can
turn the same walk threatening, with the head dropped under the shoulder line and the shoulder blades working, or
light and springy, with the body upright and each leg raised and folded high.

### LOC59. A four-legged walk never squashes like a human
stages: blocking, checks

Within each leg pair the back foot lifts the moment the front foot lands, so a four-legged walk has no human-style
squash while both feet are down; each end still dips. A walking animal spends roughly half its time on two feet and
the rest on three, never on four and never on one. From rest it lifts a hind foot first, then the front foot on the
same side: the hindquarters push and the front and the head drag. Before breaking any move into parts, find out
which part of the body supplies its force.

### LOC61. A quadruped's spine shapes its gait
stages: understanding, blocking, passes

A walk has no airborne phase and a run has one. A grazing animal keeps a stiff back and floats only when gathered; a
hunting animal flexes and extends its spine and floats both gathered and stretched out. The quicker the gait, the more
the spine bends and straightens: extension, front plant, gather with a rounded back, push-off, extension. In a walk
the shoulders drop toward whichever front leg has just accepted the weight, alternating each step. Seen from above,
the shoulders and the hips rotate in opposite directions, curving the back into a soft S that straightens at the
crossing. The front leg nearly straightens at the push-off, compresses at the plant, and hangs free ahead of the rib
cage in the swing. Fast hops and bounds read as a sequence of distinct silhouettes. A stop plants the front feet far
forward, the head back and the pelvis low.

### LOC58. Walk a quadruped as two offset pairs of legs
stages: plan, blocking

Treat the animal as a rear pair of legs and a front pair, each pair walking through its own four poses (contact, down,
passing, up), with the two pairs offset in time. Footfalls usually follow left hind, left fore, right hind, right
fore. How evenly the four footfalls are spaced in time is chosen per animal and declared: a medium, long-backed build
of well under a metre at the shoulder may space them unevenly through the stride, while a tall build near 1.6 m at the
shoulder, walking easily, spaces all four at equal intervals. Pose each pair's contacts before anything else, next
their lows and highs, and the passings last. The back line rocks like a seesaw: each end is highest about two frames
after its own legs cross and lowest about two frames after its own foot lands. Draw or start the cycle from a front
contact.

The head goes down with the chest and comes up a couple of frames after it, tilting as it lifts, and keeps one chosen
nod relation with the front foot. Ears trail the head by a couple more frames. Every key shows the mood in the ears,
the neck and the tail. The base of the tail follows the hind legs, and the remainder whips through one joint per
frame, tip last. The knees always keep a little bend. A stylised gait on long, slow steps, in which each front leg
travels together with the hind leg of the opposite side, is allowed when it is planned as clearly as the default and
declared.

### LOC64. A gallop lands in pairs with one flight
stages: plan, blocking, passes

In a gallop the legs come down as two quick pairs with a short lag inside each pair, and the body flies once per
stride, thrown by the strongest push. Which push throws it follows the build. A large or long-legged animal lands its
hind pair, then its front pair, and flies after the front push, about half a second a stride. A small, supple animal
lands its hind pair, flies after the hind push, then lands its front pair, about a third of a second a stride. Keep
one flight per stride. The spine humps as the hind legs reach forward and stretches into the reverse curve on the
push, so the body visibly lengthens and shortens. The shoulders and rump rock, and the head flattens as the shoulders
drop. A loaded lower leg bends back nearly to a right angle, and a free one folds almost as far the other way. Check
that the pairs never land together and that the flight follows the named push.

### LOC45. Judge a run contact by run values, not walk values
stages: checks, self_review

A run knee flexes 10 to 14 deg across two or three stance frames, so its frame-to-frame acceleration near each strike
is several times larger than a walk's without any visible pop. The pelvis low is sharp too, still landing one to two
frames after the strike. Walk limits for knee smoothness and pelvis acceleration do not apply to a run. Until a run
limit exists, judge the run knee by eye: no sudden step in velocity and no stall.

Sources: Epic Games, Game Animation Sample project (an Unreal Engine sample, 2024, distributed on Fab); frame-by-frame measurements of its motion-capture clips by Kei's maintainers, 2026-10-22. Measurements only, no assets; see THIRD_PARTY_NOTICES.md.

### LOC55. Run the cycle checklist on every cycle
stages: checks, self_review

Before a cycle is finished, play it at full speed, orbit the view, and check four groups.

- Feet: no foot slides while travelling; with the travel removed, each grounded foot moves backward at one even
  speed; each foot rolls through its step instead of stopping; after toe-off the heel lifts back and up clearly, a
  touch more than looks needed.
- Body: it leans into its momentum, shifts its weight from side to side, and takes a small forward surge from each
  push rather than gliding.
- Symmetry: both sides move alike, in one steady rhythm, unless a limp is intended.
- Limbs: no leg overextends; the arms swing in rotation from the shoulder, never dragged along by position; in a run
  the arms stay tight and within one or two frames of the legs.

### LOC56. Play a cycle many times before it is done
stages: checks, self_review

Repetition magnifies small faults: steps of unequal length, a slight limp, a rolling body, a foot that lifts too far,
a leg that drives into the floor. Read one cycle for these, then play it ten or more times in a row at final speed and
look again. Compare left and right step length and duration, and check the toe clearance in mid swing. Keep an
asymmetry only when it is a declared trait. Pause on every passing and crossing frame and look through the final
camera: the far arm and leg must stay distinct from the body and from the near limbs. If they do not, change the pose
slightly or report the issue to whoever owns the character's materials.
