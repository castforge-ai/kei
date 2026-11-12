# Game animation

kind: subject

A game clip is played by an engine when a player asks for it, joined to other clips, looped, blended and compressed.
These rules cover how Kei builds a set of game clips, authors them on an engine rig and brings them into the engine.

### GAM1. Name every clip gameplay or cinematic
stages: brief, plan

The brief states whether a clip is gameplay or cinematic. A cinematic is a short film with a fixed length and a shot
camera, so the film rules for staging and pace apply to it. Gameplay has no fixed running length, because the player
decides how long it lasts. It is made of clips the engine can start at any moment, repeat, and leave at the frame its
logic needs. Where a film habit and a game need disagree on gameplay, the game need wins: response comes before a long
anticipation.

### GAM2. Write the control line before keying a player clip
stages: brief, plan

For each player clip the plan records the input that drives it, when it may start, when it may be left early or
interrupted, and which clips it blends from and into. The first visible change lands on the frame after the input. If the outcome needs time, a small
immediate signal answers the button while the outcome builds. Weight is then shown after the action, in the
follow-through, the recoil, the pose it holds and the reaction. A slow start is never where a player move gets its
weight.

### GAM8. Ask about the cancel window before timing a one-off move
stages: brief, plan

A one-off move such as a swipe leaves the hub fast and lands back on it. Before timing it, find out whether a cancel or
interrupt frame exists. With one, author the full tail as in GAM7. Without one, each recovery frame is time in which
the player cannot act, so the recovery stays as short as its weight allows. It should read as the planned risk of the
move, never as dead time.

### GAM31. In a game, the body carries the character
stages: brief, plan, blocking

The player rarely sees the face up close, so attitude and emotion read in the body. Personality shows most in the idle and
its breaks, in reactions to hits, and in winning and losing clips. The brief notes how the character sees itself and one
habit, and each gets a clip. An idle break is one gesture held long enough to read, and an emote takes its speed from
its cause. Characters met together differ in tempo and posture. Whenever another character changes its mind (it
notices the player, gives up a chase, switches target or calls for help) or enters a game state such as stunned,
exhausted or carrying something, a clip shows it so a player reads it at a glance with no interface; readable comes before realistic.

### GAM3. A character is a set of clips around one hub pose
stages: plan, blocking

Draw the set as a state graph before the first clip. Each state is a node and each allowed move is an arrow labelled
with its trigger. Every arrow is either a blend or a transition clip, and the arrows a player uses often get a
transition considered. One hub pose, usually the idle (a combat idle for fighting), is posed first; attacks, hit
reactions and dodges leave it and land back on it exactly. A set table lists each clip by name with its entry, its exit,
its metrics, its event frames, a complexity grade and a priority. The hub pose is stored once and pasted into every
clip that starts or ends on it, never posed again by hand, and hand shapes come from a small named set of poses.

### GAM14. The locomotion set has a fixed order
stages: plan, blocking, checks

Build and test locomotion as idle, start, cycle, stop, idle. Pose the idle first as a single frame: for a right-handed
character the left foot leads, and the stance is no wider than the shoulders. The start answers on the frame after the
input, leads with a drop of the hips, and keeps selling acceleration after it reaches speed. The cycle begins on a
passing pose, with the back foot of the idle lifting. The stop comes almost to a dead halt while the body reacts above
it, then settles into the same idle. Starts and stops exist from either foot and are authored, not mirrored. A
four-legged start leaves from a pose where a hind paw can lift, and a change of gait needs its own transition clip
rather than a weight blend. Each start, stop or turn is a weight shift keyed with the planted feet locked. A start
reaches full root speed within a short ramp while the body keeps the look of acceleration, drives off the leg on the side
of the new direction, and ends on the first frame of the cycle, so the lean into the speed is keyed, not blended.

### GAM41. Plan a locomotion set in pairs, from both legs
stages: references, plan

When reading a measured start, stop or turn, use only the stretch where the speed changes, between the steady
steps and standing still; the steps before and after it are staging. Plan a set of your own in the same shape. Starts and stops come in pairs, from and
back to the hub, with enough steps to reach a steady speed. Turns at named angles (45, 90, 135 and 180 deg) go out and
back, pushed off from either leg. Wide and tight turning circles are entered from a short straight. Small repositions
for other characters stay apart from player starts. Keep one clean version of each motion.

### GAM19. Declare what the engine simulates
stages: rig, plan

Before keying, list the parts the engine will simulate, such as a cape, long hair, soft tissue, ragdoll deaths and
flinches layered on hits. At runtime those parts keep moving across clip changes and hide blend seams, so any keys on them are only a preview. Every
part that is keyed keeps its own overlap through starts and stops. A rigged tail is a chain of joints, so one smooth
curve along it needs a spline or a smooth skin.

### GAM20. On a new rig the method carries, the numbers do not
stages: rig, understanding, blocking

When a method moves to another rig (an engine rig, a retarget, any new body), keep the method and its targets on
derived measures: a knee angle, a toe height, the angle of the foot to the floor. Drop its control values, such as reach
fractions, roll amounts and offsets; a reach value that gives a soft knee on one rig can give a 20 deg knee on another.
Probe the sign of every channel first. Then reach each constrained pose by searching for the key value that hits its derived target, with
bisection or one channel at a time, reading the result on the rig as the engine evaluates it and setting keys only. Read the whole cycle again
afterwards.

### GAM22. Know where the leg IK stops
stages: rig, blocking, passes

Many engine rigs rest with straight legs and a leg IK that does not stretch. On such a rig, raising the pelvis to its rest height or
higher pulls the planted foot off the floor, and near a straight knee small pelvis changes become knee pops. Make
each contact with the knee bent about 12 to 15 deg, and keep a planted knee at about 7 deg or more. A foot roll control has a working range, and past
it the foot can fold back on itself. Find that range by probing and never key beyond it.

### GAM23. A solver target carries its guards
stages: rig, passes, checks

Every target a solver chases states the usable range of the control it drives, a floor and a maximum change per frame,
and the search stays inside those bounds. A search that drives a control past the rig's fold point makes the part
flick, and one with no floor rolls the toes into the ground, so the toe never dips below the floor during the search.
Near a toe-off or a heel strike, cap how far the control may change in one frame, so the first swing frame does not
whip. Never snap a joint limit to its nearest end. A plain IK chain straightens a dangling leg in one frame when its
target drifts out of reach; give free legs a soft reach limit so the knee keeps its bend. Read the target where the motion actually happens, which is
often a frame between two keys. The solver sets the values of pose and breakdown keys; a denser set is allowed only while the curve
across it stays smooth, never keys on every frame chasing a number into noise.

### GAM24. Test a new measure on a known pose
stages: checks

Before a solver chases a new derived measure (the swing of an arm relative to a tilted trunk, the turn of a head, an ankle angle), key a
known pose such as rest, read the measure, and confirm both its value and its sign. A measure that subtracts the wrong
quantity, such as a trunk lean subtracted instead of added, drives a solver confidently in the wrong direction, and no
check notices, because the check uses the same reading. Before a solver relies on a derived measure, also confirm it
against mesh captures.

### GAM25. Measure from the evaluated rig
stages: checks, self_review

Take every derived read (knees, contacts, centre of mass, pelvis curves) from world transforms sampled on the evaluated
rig in the engine, not from control values. Pause playback before sampling, and sample long ranges in chunks when a tool
caps its sample count. When an engine tool lacks a capability, name the gap; never fake the result. Tools return
numbers and images, and the judgement stays with Kei, the critic and the person who signs off. To review a travelling clip in place, work
on a duplicate and offset the whole actor backward by the root travel; the rig keys stay as they were.

### GAM28. Push one clip through the whole pipeline early
stages: rig, deliver

Before the first real clip on a new engine or rig, run a test export and learn two things. First, what arrives
intact: position keys, bone scale, props, cameras and any extra data the engine reads. Second, what goes wrong: the
settings that break the rig, the causes of a failed export, and how the frame range and the character to export are
chosen. Then take one rough clip from start to finish. The weight class
must hold in every clip of the set. Set the engine
playback beside the authored clip at matching frames and compare contacts, arcs, accents and hand and foot locks. A difference is nearly always
an error on the animation side, so look there before blaming the exporter. Typical faults are a frame offset, an added
time scale, collision that does not follow the root, one bone too many or too few, an additive with the wrong reference pose and
bad skinning. To find which layer fails, replace one part at a time with a version known to work: the asset, the viewer
or the file.

### GAM34. Rough it in early, polish the most-seen first
stages: plan, blocking, passes

Put each clip into the game rough and early, so faults between clips show while they are cheap to fix. Block with the
root alone first for rhythm, then key the whole body on the same frames with no offsets. Polish the clips the player
sees most first, and keep the quality even across the set, with no gulf between a polished clip and its neighbours.

### GAM15. Slice joined clips from one parameterised timeline
stages: plan, blocking, passes

Build the joined clips of a set (take-off, air, landing; start, loop, stop) on one timeline and cut it into touching
ranges that share their boundary frame, so each join is exact. One generator script builds the shot from named
parameters. Every pass and every revision is stored as its own named set of parameters next to its output, and a note becomes a
change of parameters, never a hand edit to a copy of the script. Blend lengths and clip names are parameters too. After
any change to the generator, rebuild older passes from their stored sets and confirm nothing in them moved. A value
that design is likely to tune, such as the arc height of a jump, drives the whole clip from one parameter, ships with
its safe range and is checked at both ends of that range.

### GAM9. Player attacks answer at once; enemy attacks warn
stages: plan, blocking, passes

Keep the player's attack near instant. Allow at most 2 frames of engine blend from whatever was playing, and cross
from the loaded pose to the contact pose in a straight cut or with no more than a couple of in-between frames. The anticipation budget follows weight: one or two frames for a light move, more for a heavy weapon
or a big fighter, never none for a move that must feel heavy. The strike drags head, then body, then arm, keeps its
crisp arrival frame, holds a readable result pose and declares its hit window. Every key of a short attack carries the
intent, because hit-stop and photo modes show single frames. An enemy wind-up is the cue the player reacts to, so it
keeps a full anticipation of about 1/5 s (6 frames at 30 fps) or more. Long holds belong to enemies, other characters
and cinematics, never to the player's own move.

### GAM7. Author the whole follow-through and mark where control returns
stages: plan, blocking, passes

Key all of the follow-through and all of the settle, and keep the strong final pose on screen until it reads; that hold
is a moving hold, never a dead freeze. Mark the hit frame, and mark the interrupt frame from which the player can act
again. Only
the playable part, from the input to the interrupt frame, has to be short. The tail after it plays out when no input
arrives. Never trim a clip to gain response.

### GAM11. Hit reactions are short, directional and even
stages: plan, blocking, passes

A damage reaction is exaggerated, moves away from the blow and stays short. Every hit direction gets the same treatment
and the same length. Hit-stop is an engine event placed on the accent frame, not keys inside the clip. A reaction never
starts before its hit frame, and a stall before it feels like lag. Animate the contact against the hit zone, with no
pass-through, and pick the reaction by the zone that was struck. A player reaction stays short and blendable, while
other characters and cinematics may land a held attitude. A hit that reads flat gets a bigger extreme and a root shift on
the accent frame, with the shift checked against the capsule and declared.

### GAM13. One collision capsule for every clip
stages: rig, blocking, checks

A character's world collision keeps one shape across all of its clips. On every planted frame the feet reach the bottom
of the capsule, so the character stands on its collision, and no pose sticks far outside it. When hit and hurt volumes
are proposed, they lean in the player's favour: the player's own damage volume is kept smaller than the visible body,
and an opponent's striking volume is kept smaller than the part that strikes. Design owns the volumes; the animation owns the poses that fill them.

### GAM32. A cutscene joins gameplay like any other clip
stages: plan, blocking

Open a cutscene on the continuation of a player action, such as a vault or a door, at the same speed and facing. When
the entry speed is not certain, keep the character out of the first shot and let it walk in; a player who arrived at a
run must not appear strolling. A cut is allowed to relocate the character. In the final frame, both the body and the
camera point toward the player's next goal. A look into the camera belongs to cutscenes only.

### GAM39. Climbs pass through one shared cut pose
stages: plan, blocking

Design one pose that every climb height passes through, such as both hands on the edge with the hips just below it,
and start every ending from it, the lowest step-up included. Author the hand and foot contacts against the standard prop heights, name their
frames, and plan how the engine aligns the character to the object on entry. The root or capsule gets a separate track that
never cuts into the wall or the ledge, since an interrupted climb can otherwise leave the body inside the wall. On each grab frame the
hands sit on the edge and the body faces the wall square.

### GAM33. Measured motion is a first pass
stages: references, passes

Captured or measured motion, including a sample set shipped with an engine, never ships as the finished performance.
Rework it in a fixed order. Pick a take that ends close to the wanted final pose with no shuffle steps. Mark its key
poses. Change its timing unevenly, so a strike gets quicker and a follow-through gets longer. Then exaggerate the key
poses beyond what was recorded, for a clearer silhouette and line of action. Meet the hub idle through offset layers, and join takes inside motion rather than at rest. Declare every push
past the measured value. A loop made from measured walking spans at least three steps and blends the third back over
the first, rather than forcing the last frames onto the first.

### GAM42. Generated motion fills; the defining clips stay authored
stages: plan, checks, self_review

When a system generates or fills motion, whether procedural, learned, matched from a bank or built by Kei's own
generator, the clips that define the character are authored or judged by hand: the hub idle, the signature moves and
the key reactions. The fill must carry weight and momentum through every join and stay directable, so a note applied to
it shows. Generated output faces the same checks and the same eye as keyed work. At each join look for a pop, a float
or a stall, and ask whether the result plays as an acted move or as a blurred mean of many.

### GAM4. Every join matches pose and velocity
stages: blocking, passes, checks

A clip begins on the exact pose the clip before it ends on, moving at the same speed in the same direction. A cycle
continues from the final frame of the clip that leads into it, and any clip that leaves the hub opens on the hub pose. Check each join twice: measure the pose
and velocity difference at the boundary, then step across it one frame at a time by eye. A set is not finished while
any join is unchecked. The same holds inside one shot wherever one action passes to the next, and across a cut: the
part in motion carries on at the same pace and heading, so nobody can see the hand-off.

### GAM38. An exit enters the next clip at the matching frame
stages: plan, passes, checks

For every way out of a cycle (a stop, a cancel, a transition), build an entry table. It pairs every cycle frame with the
target frame nearest to it in pose and velocity. The legs then carry on in phase: from a passing position the exit
picks up on a similar passing position, and from wide-open legs on wide-open legs. When a follow-up can fire anywhere
inside a window, start it from a pose taken late in that window, so a late trigger never pulls the pose backward. Through
every such blend the root and any weapon tip keep moving forward along the action. Test by triggering at the start,
the middle and the end of the window.

### GAM16. A blend is an in-between nobody keyed
stages: plan, passes, checks

Plan each blend: the foot phase on both sides must agree, and the momentum must carry through. A one-frame contact or
hit can vanish inside a blend, so no such event sits in a blend window unless that is the intent. Choose each blend
length by feel, a few frames that trade smoothness against response, write down its frames going in and coming out, and
deliver it as a tunable value rather than a fixed number in code. Fix a pop with blend length and an interrupt frame, not with more
keys. Step through every join in the engine.

### GAM37. Blend partners share their phase
stages: plan, blocking, checks

Clips blended by a parameter, such as walk and run by speed or flat and uphill by slope, use the same lead foot, and each
contact falls at an equal share of its cycle, within about a frame. Lean, bounce, elbow bend and knee lift may change
between partners; the phase may not, so a speed set is planned as one. Split a strafe set into two families, the clips that face forward and the clips that face back, and blend only
inside a family. Where the hips must switch between the two, author both over an overlapping range of
angles so the switch has room, and place it by how the run twists. Play the halfway blend: the legs must not scissor.

### GAM18. Upper-body clips must sit on any legs
stages: plan, passes, checks

A partial clip played on the upper body has to read with only the head, chest and arms. Its influence is feathered up
the spine, with more of the partial clip high and more of the locomotion low. Check it over every locomotion it may play
on, such as idle, walk, run and strafe, for a broken waist, a floating chest or arms that fight the counter-rotation of
the legs. Additive layers and procedural noise stay consistent from frame to frame, and each additive is the
difference from a named reference pose, usually the idle. Play every additive over each base it may meet and keep the
summed pose inside the joint ranges.

### GAM5. A loop closes on its own seam
stages: blocking, passes, checks

The final key of a cycle sits on its last frame and equals its first key plus one cycle of travel. Once the travel is removed, no joint ends more
than about 1 cm from where it started, and the jerk across the seam stays below twice the 95th-percentile jerk found
inside the cycle. Match velocity and curve tangents at the seam as well as the pose. Key some extra frames past both
ends of the range that will be shown, so no visible frame carries the ease at the end of a curve. Judge the loop on its
seam, not from its middle.

### GAM36. A loop hides where it ends
stages: plan, passes, checks

Inside a cycle, spread the peaks: the root, the head, the arms and the loose parts each reach an extreme on a
frame of their own, and no single frame looks like the end. No gesture or accent stands much larger than the rest, because one loud beat announces
every repeat. A distinctive gesture goes into a variant or a cycle breaker instead. The player's own cycles may carry
strong character; cycles shared by many characters stay plain. A cycle breaker leaves the hub and returns to it, keeps
close to the hub's silhouette the whole time, and must survive being interrupted at its widest pose: a start blended in
from there shows no jump.

Any short loop, such as a breath, a sway or a loose part, needs at least three distinct states per cycle. Its key point
loops round an oval or an eight; a point that retraces one line reads as jitter.

### GAM6. Loops are watched hundreds of times
stages: plan, passes, self_review

Set the length of a loop from two things: how much the action repeats, and how long a player stares at it; avoid an exact repeat shorter than about
8 frames at 30 fps. Loops layered on one character have lengths with no common factor, and a crowd runs four or more
cycles out of phase. Review a loop over ten repeats, checking the seam, symmetry and clearance each time. An idle never
lets every channel come to rest, yet planted idle feet and a locked weapon arm must not shimmer. Squash on a game rig
lives mostly in the pose, and any squash returns to the model inside the loop.

### GAM30. Judge a game clip in the engine, on the game camera, with the controls
stages: plan, blocking, checks, self_review, deliver

A clip is not done until it has played in the engine on the game camera, driven by the input, chained with its
neighbours and seen from every side. The viewport of the authoring tool is a step, never the verdict. The gameplay
camera can sit anywhere and often sees the back, so each pose is checked from front, back and both sides and never cheated
toward one camera, and the read lives in the silhouette and the head angle. From blocking on, build a camera that
follows the character's position but not its rotation, at the planned play distance and height, with the game's field
of view, and render the blocking on it at the game rate next to the review views. Ask whether the move reads at play
size, whether a turn of the body reads against a camera that stays still in rotation, and whether the speed feels
right. Get a first rough onto the real character in the engine as early as possible. Retargeting and compression copy the motion and can lose its life, so the clip in the engine is set beside the
clip as authored. The final question is whether the move feels responsive and does what the player meant.

### GAM35. Hard failures are physical; style is a note
stages: checks, self_review

Only objective physical errors fail a game clip: foot slide, floor penetration, a leg reaching past its length, a walk
with a flight phase, crossed legs, and a pop at a loop seam or anywhere else. Style findings are written as notes. Film
work may allow a little foot slip on a fast cartoon run; game work never does.

### GAM17. Tune a timing value by bracketing it
stages: passes, self_review

If a blend or a frame count feels off, try a value certainly too far in the opposite direction, then keep splitting
the interval toward whichever side felt better until it lands. Stepping one frame at a time wastes trials and can
overshoot. If several causes could explain a fault, alter a single thing per test and name that change in the version
note. Log each trial
with its value and whether it played too fast or too slow.

### GAM40. A retarget pins the feet, never the arms
stages: passes, checks, deliver

When motion moves onto another body, solve the feet to the ground so they do not slide. A hand is pinned only while it
grips a fixed object, such as a ladder rung; forcing the hands onto the source path everywhere bends or overextends
the arms. Inspect each clip after the transfer for the same clavicle or spine bend turning up in all of them, for fine detail
smoothed away, and for slide on planted frames. A retarget onto a different build keeps that build's weight class
and character, so two bodies never share one motion unchanged. A bad retarget is redone, not patched later.

### GAM26. Export samples every frame; one-frame events must survive
stages: passes, checks, deliver

The engine receives every frame at the project rate and interpolates linearly between them, and compression may keep
only every second frame. Author at 30 fps on ones; for a 60 fps game, let the engine interpolate. After export at the
game's compression, check each one-frame event such as a contact, a hit pose or a snap, and when one goes soft or disappears,
give it a held frame or a slower approach so half the samples still catch it. The engine reads quaternions while keys are often Euler
angles: fix a gimbal flip with the rotation order or a gimbal mode, never with a flipping curve, and watch big turns for
the long way round. A repeating element strobes once it moves more than about a third of its spacing per rendered
frame. Motion trails and blur are engine effects, not rig keys.

### GAM27. Import settings belong to the clip
stages: deliver

Declare each clip's import settings with the clip: whether root motion is used, whether the root is locked, the additive
type with the pose it is measured against, the compression and the play rate. Set compression clip by clip during production, not as one blanket value at the end,
and raise a clip's fidelity when it loses its read.

### GAM29. Name exported clips from general to specific
stages: deliver

Build each clip name from broad to narrow: the skeleton it plays on, what it does, then the variant, with an
optional zero-padded number, as in quadruped_trot_turn_right_02. Use whole words joined by underscores, no spaces, and
only characters the engine accepts. Store the files in a shallow tree that follows the same broad-to-narrow order: one level
per skeleton, and under it one level per gameplay feature (movement, combat, traversal and so on). Keep experiments in
a scratch area and retired clips in an archive area apart from live work instead of deleting them, and leave no unused
clip in the engine. Each export carries the name of the scene it came from.
