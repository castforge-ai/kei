# Follow-through, overlap and secondary action

kind: principle

Parts of a body do not move as one block. These rules cover how Kei makes force travel down a chain, how loose parts
drag, follow through and settle, and how small secondary business is added without stealing the action.

### OVL1. Drag, overlap and follow-through are one mechanism
stages: understanding, plan, passes

When a driver starts, the parts hanging from it stay behind for a moment: that is drag. When the driver stops, those
parts carry on for a moment: that is overlap or follow-through. The joint-by-joint delay down a chain, and lead and
follow, are other names for the same lag. In review, drag tells what lags; the order in which the joints bend tells how
to fix the timing. Nothing in a body starts or stops all at once, and the follow-through is a result of the main
action, never a second action laid on top.

### OVL2. Only the driver supplies force
stages: understanding, passes, checks

A trailing part gets its motion from three sources only: its parent pulling and speeding it along, gravity on its
mass, and the air. Weight counts only while the body is supported; in free fall body and tail drop together, so
the tail feels no extra gravity. The tip never moves by itself. Never place a section of a chain on a target or hold
it in a pose; every bend is something the driver's motion pushed down from the pin.

### OVL3. Force travels down a chain one joint per frame
stages: understanding, passes, checks

Every segment is pinned to the far end of its parent. The root reacts first and the tip last, so in a chain of four
joints the tip answers the driver four frames later. A joint the push has not reached yet is simply towed along by
its pivot, trailing it. A simple way to build it: each frame, turn each joint part of the way (about three quarters)
toward the direction its parent pointed one frame earlier. The same delay shows at every scale: a heel comes off the floor
ahead of its toe, and the shoulder, arm, hand and fingers arrive one after another.

Because each joint copies its parent a fixed delay later, a ripple is a pattern that slides along the chain. An
in-between is that pattern moved on, never a blend of two key shapes, which flattens the bend.

### OVL4. Put overlap in the poses and judge it in world space
stages: blocking, passes, checks

Key the overlapping controls on the breakdown frames so each frame shows the lag. Never shift whole curves by a frame
in the graph editor to fake it; a plain curve offset suits only a simple trailing part such as a tail. A breakdown can
carry overlap by itself: tip one feature the other way from the main move, for example the skull rising while the
nose tips down, and the in-betweens get the overlap without extra keys. Drag is often a counter-rotation keyed on the
parent's existing frames, so a local curve can start on the parent's frame while the part still lags in the world.
Measure the delay in world space, not by reading local curves.

### OVL5. The driver's timing decides the overlap
stages: plan, blocking, passes

Set the driver's duration and the kind of stop before touching the chain. A move over two frames throws the chain
almost level and can flip it, which is a whip and must be declared. A move over twenty frames leaves only a small
trail. A stop has to be sharp to throw a loose part; a gentle ten-frame roll to rest produces almost no
follow-through.

### OVL6. The root turns only as hard as it is pulled
stages: passes, checks

The base of a trailing part swings toward the pull acting on it, in proportion to how strong that pull is. A slack
pull turns nothing: a trailing part stays as it is until whatever drags it has taken up its slack, and only then
swings into line and starts to travel. Close to the top of an arc there is almost no pull, and the root should not
whip round to face the new heading. The follow-through begins while the driver is still slowing down, well before it
comes to rest.

### OVL7. Size the overlap by speed, weight and looseness
stages: plan, passes, self_review

A fast driver and a heavy, loose part give a large lag; a slow driver gives a small one. Let the lag grow with speed
and never copy one fixed offset down every chain; identical offsets read mechanical. Treat the lag as an outcome to
look at, not a value to hit. The timing has to be exact: a single frame too slow already feels rubbery, overlap on
every part is a tangle of waves, and none at all looks dead. Push it only where the moment calls for it, and ask how a
real body would do it, so nothing flails. When there is too much, scale the values down and keep the keys where they
are. Lower sections bend further than those above them: scale each section's bend a little up from its parent's,
about 1.1 to 1.3 times, without moving a key. Overlap never rescues a weak or choppy pose; fix the pose.

### OVL8. A moving driver leaves its tail along its path
stages: blocking, passes

While the body travels, the trailing part lies back along the route the body just covered: rising, it runs down
behind toward the last contact; past the top, it arches back over the peak. A change of direction runs down the tail
as a wave. A tail that keeps a rest shape and only swings from side to side is wrong.

### OVL9. At a dead stop the tip keeps going
stages: blocking, passes

When the driver halts hard, as in a squash, the tip continues on its own heading and the chain bows; on the next frame
it lines up with the new path. Across an impact this change can take a single frame. The first swing after the stop
goes the way the tail was already travelling, never toward the side its rest pose sits on. It then overshoots rest,
returns on a reduced swing and settles, with the tip coming to rest last.

### OVL10. A chain is one smooth curve on every frame
stages: passes, checks

At any frame the chain forms a single C or S, drawn thick to thin, never a zigzag. Limit the bend between neighbouring
segments so the tip never hooks. Between two frames a segment rotates at most about 35 deg, except on a
declared whip snap. A joint limit keeps the part on the side it already occupies; a limit that jumps to the closer end
of its range throws the part from one end to the other, feeds energy in and makes endless sway or half-turn flips.

### OVL11. A tail is fixed to the body at one point
stages: rig, blocking, passes, checks

Attach the tail at one spot on the surface, such as the rear of the body's long axis, and let that spot travel with
the squash and stretch. Keep the root aimed into the rear half (roughly 100 to 260 deg from forward). A pull aimed
forward presses the root against that limit and stops it there. Pivoted at the middle of the body, a tail would exit
at a new place on each frame and stop looking attached. On a free pivot a tail can also wind around a body that
rotates, so a ball or any body carrying a tail does not spin. Never set each segment straight onto a target: the tip
then moves by itself until the chain comes apart. Judge a follower against the path of its driver, never against the
trail of its own tip, which hides the fault.

### OVL12. Weight, stiffness and air set the timing of a loose part
stages: plan, passes

A stiff, springy part swings back fast and comes to rest in two or three swings. A light ribbon or veil has almost no
spring; the air shapes it and it drifts to rest, its small jolts lost in the drag. A heavy cloak holds on to its momentum
and direction when the shoulders alter theirs. A creature's tail is held up by its own muscles: treat its weight as
carried, so a fall does not lift it and a landing does not make it sag or balance upright and topple.

Decide for each loose piece, such as a lock of hair, whether it is a design shape that keeps its form or a follower
that drags with a little stiffness. Give the followers different amounts of looseness.

### OVL14. A whip is a wave that ends in a snap
stages: plan, blocking, passes

The bend of any wave runs from the root toward the tip, both on the outgoing swing and again on the return, with a
cushion at each end. The return takes different shapes from the outgoing swing: the tip trails in both directions,
and each reversal starts at the root, which puts an S in the chain at the turn. Followed over a full swing, a clean
wave's tip draws a smooth path that loops back across itself in two lobes, like a figure of eight; a tip that only
runs straight back and forth means the wave failed. When an outside force enters at one point (wind, a jerk, a blow),
locate that point on each frame: it leads, and everything past it bends behind. In cloth or a chain, the bend reverses
one section per frame, so a single curve turns into an S and then into the opposite curve.

A whip is that same travelling bend brought to a sharp finish. The viewer's attention is held by the frame placed
right before the crack. The crack itself occupies a single frame, the tip goes slack on the frame after, and its
settle stretches over many frames. A small action repeated beat after beat is a run of such snaps; OVL17 gives how its
beats are shaped and timed.

### OVL15. A wave in steady wind has no keys
stages: plan, passes

Build a flag, banner, cape or tail rippling in constant wind by moving one crest along it, not by posing keys. The
crest runs from the fixed end to the free end at an even rate and never backs up; the loop closes when the next crest
reaches the spot where the first one began, so the loop lasts the crest spacing divided by the crest speed. On a rig,
this is a fixed phase delay from joint to joint. When a move blends into a cycle, carry at least one whole wave through
the change, and two after a violent move, so the wave from the move meets the cycle's own wave with no reset. A cycle
animated frame after frame from its first frame has its end matched back to its start before delivery.

### OVL17. A part that stops dies off
stages: plan, blocking, passes

After the body stops, a loose part makes two or three shrinking swings at an even half period (8 frames is typical),
one key per extreme with flat tangents, then rests. Key the child where the parent is between extremes, swinging the
other way and less each time; on the parent's extremes the child is back at its base. If the swing is too big, scale the values; if it
jiggles, spread the keys apart and keep the values. Keys may run past the last frame so the curve is still alive at
the cut. Cartoon timing cuts the settle well short of where a real swing would end; the shot ends 1 to 3 frames after
the part comes to rest. A part that swings without dying off looks aimless.

A small action repeated beat after beat, driven from the body, dies off in the same way, each beat a little snap of the
kind in OVL14. In a coughing fit, for example, the head travels round a loop, over and then back, the shoulders lift
each time the head comes down, and the hair flicks past at every reversal. The beats shorten by about a third as the
action winds down toward its settle, for instance from 6 frames apart at the start to 4 near the end at 24 fps.

### OVL18. Never stop every part on the same frame
stages: blocking, passes, checks

Hold back at least one part to land after the body. The torso comes in and slows with the head still trailing, and the
head catches up a beat later. If every part lands at once, nothing is left over to overlap. The start of a reaction
works the same way: the body goes first while one part, such as hands resting on the belly, stays where it is and
gets a later beat of its own. A sudden stop needs more overlap, not less: a deer braking from a sprint takes the load
in its forelegs first, its hind legs a couple of frames after, and its ears and tail last. The body's settle ends
early, on a moving hold, while a prop or a loose piece is keyed separately (swing out, flap back, reverse, settle) and
comes to rest later and over more frames. Where several identical things move together, such as a set of hanging lamps,
shift a few of them by a single frame, some late and some early; exact sync looks dead.

While the main mass comes to rest, some smaller part is still arriving, and the next move begins somewhere in the body
before another part has finished settling. When any part acts on its own, such as a quick head move, the hips answer
very slightly. Just before an action, a tiny rotation against the coming move, about 0.3 to 0.4 deg, keeps its start
alive. Inside a hold, size the overlap so the pose stays alive without blurring.

### OVL19. A settle staggers the root, then the head, then the limbs
stages: blocking, passes

The end of a move eases into its final pose and never lands sharp. Copy the end pose to the last frame, then stagger
the arrivals. The root's height arrives first and overshoots while its forward travel is still finishing; the head
follows, and the limbs come in at the end, upper arm ahead of forearm. Add a middle key that pushes each root channel a tiny amount
past the final, in the direction it was already moving, one channel at a time. Then a living hold. Overshoot grows
with speed and mass. Size the settle by the energy at the contact, not by the anticipation: landing at the top of a
jump up gives a light, slow settle; landing from a fall gives a deep, fast compression and a long settle. Stop before
the limbs turn floppy.

For a game move, mark an earlier frame where the player may interrupt, but still author the whole settle.

### OVL20. Settling removes motion; it never adds any
stages: blocking, passes, checks, self_review

Work the settle as its own pass after the main action and the contacts are right, and step it frame by frame. The
work is to let the motion the object already has fade out well; nothing turns back by itself. A rock or a swing back
is allowed only when something causes it: a slope, a flat face, an off-centre weight, a squash springing back, a
pendulum's restoring force, or a living body that chooses to. A round ball on level ground has no such cause: it keeps
rolling, slows at an even rate until it stops, and gets no rocking and no drift backward. Speed that a travel channel
has gained fades gradually unless a contact halts it. Where the travel curve changes slope, a tight cluster of keys
marks a hitch; rebuild that stretch instead of nudging it.

### OVL21. After an impact there is no flat frame
stages: blocking, passes

The squash keeps deepening for 1 or 2 frames after the contact, rebounds a little past rest, then settles with
shrinking changes. Key that overshoot and settle as poses already in blocking.

### OVL23. Force can also travel back up a chain
stages: passes, checks

A child that stops hard pushes on its parent: a forearm that snaps straight and locks jolts the upper arm. The
one-joint-per-frame delay describes force moving downward from the driver, so look for this bump whenever a lower part
stops abruptly.

### OVL24. The far end of a limb trails its root
stages: blocking, passes

When a limb starts to move, its far end is the last to go: a reaching arm leaves its hand behind for a moment, a
rising leg leaves the foot hanging, and anything held loosely swings after the hand. In a walk the hip goes first and
draws the thigh after it; knee and shin trail into a bent leg and only straighten as the heel reaches the contact. An
arm reverses from the top down. The upper arm turns back first; forearm, wrist and hand follow in that order with
at least a frame between each, so for an instant parent and child travel in opposite directions. Never reverse every
joint on one frame.

### OVL25. A carried object adds weight and its own lag
stages: plan, blocking, passes

Anything the hands carry, light or heavy, in one hand or in both, adds weight and a lag of its own; an arm held up on
guard and any cloth or hair hanging from the body follow the same logic. With an object in one hand, such as a tool,
a bag or a long pole, the carrying arm swings through roughly 50 to 70 % of the free arm's range, and to balance it
the free arm swings wider. The far end of a long held object trails the hand by 1 or 2 frames at each change of
direction, overshoots a few degrees and settles. At each foot contact that far end dips and settles 1 or 2 frames
after the pelvis reaches its low point. On the carrying side the shoulder drops 2 to 4 cm and sits back, and the
torso leans 1 to 3 deg to the other side. The lag shows at the wrist, not the elbow. An arm held on guard, with or
without anything strapped to it, moves as a counterweight, and loose cloth or hair drags on its own curve and settles
after the body.

### OVL26. Rotation follows a change of path 1 or 2 frames late
stages: passes

A light object drifting through the air, such as a sheet of tissue paper, tilts along its direction of travel and
dips into each dive. Each change of rotation comes 1 or 2 frames behind the turn in its path, never ahead of it. A
corner, a fringe or any other attached part trails the body by the same 1 or 2 frames at each curl.

### OVL27. A load riding a part leaves after the extreme
stages: passes

Water, sweat, dust or a loose strap end carried by a moving part separates on the frame after that part reaches its
extreme. From there it keeps the old direction and follows its own falling path.

### OVL28. Finish the body before the trailing parts
stages: plan, passes

Refine the body's curves until they are final, then add the overlap of tails, hair, capes and ears; any later change
to the body invalidates the overlap. Animate each extremity forward from the finished body, from its action, its
weight and the air, never by keying it on the body's frames; the loose part often reaches its top speed at the very moment the body comes to rest.
Decide in the plan whether a trailing part is passive or acted. A passive part gets its follow-through from the
root's momentum, with nothing keyed. An acted part, or a pendulum whose top is the driver, has its root keyed on its
extremes and the delay carries them down. Copying those extremes down section by section, 1 or 2 frames later each
time and with only the values scaled, works for a simple chain seen from the side; in most other cases study the
motion and key each section. If the rig lacks a part, such as a ponytail, say so; never fake it.

### OVL30. Similar parts never move in unison
stages: passes, checks

Fingers, folds of cloth, locks of hair, leaves or members of a group each get their own amplitude, speed and timing.
Matching values on matching parts read as a machine.

### OVL32. The ending is planned before the first key
stages: plan, blocking

The follow-through ends on a pose that is clearly caused by the action and is held long enough to read. For each main
action, draw small sketches of what happens after it and of the recovery, and give them poses and timing of their own,
often lasting longer than the action itself. The way a move finishes describes the one making it: careful,
careless, triumphant. For a player-controlled game move keep the follow-through short and cancellable; a cinematic or
a non-player character keeps the full length.

### OVL33. Secondary action supports the idea and stays below it
stages: plan, passes, self_review

Add secondary business, such as straightening a collar while waiting for news, only when it serves the one idea of the
beat. Size it so it neither takes over nor turns mushy, and never let a hand or a prop cover the face while it acts.
Work in layers: first the main action, finished and signed off; next the secondary laid over it; last a pass that
makes everything else agree with both. Small touches go in last: a squint on an effort, a hair flip, a little hop of
the feet to reset the stance, a finger wiggle. Outside a few transitions, any paused frame should still show the main
emotion; nothing secondary upstages it. Arms and legs take part in the action; they are neither frozen nor drifting
with no purpose, unless the acting chose a held pose.

### OVL34. Judge drag frames at speed
stages: checks, self_review

Soft flesh and loose parts trail the skeleton by 1 or 2 frames. Such a frame may look broken when paused and still be
right in playback. Key poses must read when paused; drag and in-between frames are judged playing at full rate first,
then paused only to hunt for pops. When a strange frame is intended, such as a smear or a stretched limb, write it in the
plan so a critic does not correct it. A pose that is funny as a still must also be checked in motion.

### OVL35. Review every frame of the whole sequence
stages: checks, self_review

Overlap can come apart late in a shot even when the first bounce and the stop look right, so render the entire
sequence as strips and look at all of it. Check each reversal from the side or three-quarter view, where the C and its
reverse read; viewers spot a wrong overlap at once. Step slowly through the settle for knee pops: a single-frame pop,
a first pop that is too strong as the leg lifts, or a standing leg that bends or shakes. A standing leg stays straight
through the whole settle.

### OVL36. A chain moves as one piece before it bends
stages: passes, checks

When the driver brakes hard, the chain does not break at once. For about 3 frames every section turns together in
world space while the bends between them stay as they were; then the joints open, starting at the top. A hard start
mirrors this: the sections first swing back as one. Next the bottom joint folds the other way from the joint above
it, by as much as 8 deg over roughly 9 frames, which keeps the free end in place; only then does each section trail in
turn. Holding
each section's drag value through its offset frames gives this rigid carry with no extra keys. Judge it in world
space, where the local curves hide it.

### OVL37. A follower bends most when its driver is fastest
stages: passes, checks

A trailing part is nearly straight at the driver's extremes and most bent where the driver moves fastest; in one
measured swing the bend ran from about 3 deg to about 45. When the driver reverses, the follower starts to slow one
frame later but only turns round 5 or 6 frames after. A chain eased evenly from its drag pose to its first extreme
lines up too early, before the driver has stopped; a well-timed chain passes straight about one frame after the stop.
Favour the breakdown so that crossing comes late.

### OVL38. Name the lead and the order of the sections for every move
stages: plan, blocking, passes

Overlap runs through three chains: spine to head, shoulder to fingertips, and thigh to toes. Work each chain by itself
first, then judge the body as a whole. For every move, write down which section leads and which are pulled along,
even on a limb with no visible wave. Choosing the leader is an acting decision, and each main mass that can lead (a
foot, the hips, the head, the shoulders) gives the move a different meaning. Every section gets start and settle
frames of its own, so no two begin or end together. From a still stance, most large actions start low: the pelvis
sinks a little so the weight begins to fall, the trunk turns or winds up, and the motion then cracks outward through
the rest of the body. A move set off by a look may begin with the head.
