# Arcs and paths of action

kind: principle

Almost nothing alive moves in a straight line. These rules cover how Kei plans, builds and checks the paths that
parts of a character travel.

### ARC1. Choose each path before its in-betweens
stages: plan, blocking, passes

Every move gets a path chosen on purpose. A curve is the default. A straight path is allowed only for a short, fast,
powerful move such as a jab, and the plan says so. The worst path is the one nobody chose: the soft, half-curved line
an interpolator produces between two keys.

Living things, props, plants and humanoid robots all move on curves. Only a machine built to cut a straight path
moves straight. The one exception in the body is an eye dart, which travels straight and stops hard; an eye roll curves.

### ARC2. Things in free flight follow a parabola
stages: plan, blocking, passes

Once a body or a prop leaves the ground, its centre of mass rides a parabola, whatever the object does around it. Time
the centre on its parabola first. Then turn a rigid object about that centre by an even step each frame, or change a
character's shape around it. The path of the centre never bends to suit a pose.

Along the parabola the frames sit close together near the top and far apart near the ground. A bounce is a chain of rounded tops with a sharp corner only at each contact, never a V or a tent shape. A light,
large object in air drag falls more steeply than it rose and stops speeding up near the bottom, which reads as floaty.

### ARC3. Turning parts move on circles, and bones keep their length
stages: blocking, passes, checks

A part that rotates about a pivot travels on a circle around that pivot. A swinging arm is two links: the upper arm
circles the shoulder, the forearm circles the elbow and lags behind it. Any frame where a limb or a pendulum looks
shorter than its rest length is a fault. Measure bone length per frame when in doubt; it must not change.

### ARC4. The breakdown makes the arc
stages: blocking, passes

A breakdown placed halfway along the straight line between two keys gives a straight path. Only a breakdown placed off
that line, on the intended curve, gives an arc. Rotating a joint in forward kinematics curves on its own. Moving a
control by position (the pelvis, an IK hand or foot, a prop) stays straight unless its breakdown is set on the curve by
hand.

### ARC5. The root and the feet get their arcs in blocking
stages: blocking

During blocking, the pelvis and every travelling foot get breakdowns, and each follows a curve of its own. In a step
these curves point opposite ways: the hips sink below both of their keys while the stepping foot rises above both of
its keys. Move
the axes together. The hips travel down and across at the same time, each channel carrying part of the curve; one axis
after another looks mechanical.

The hips never go from one place to the next in a line. Their arcs carry the weight, and the size and shape of those
arcs say heavy or light. When many limbs move, trace the hips before anything else, and round off each straight jolt
in their path while keeping the crispness of the timing, so the result is neither soupy nor floaty.

### ARC6. A head turn leaves the straight line
stages: blocking, passes

When a head turns, the whole skull travels and dips in the middle of the turn by default. A rising middle is a valid
choice, and a flat path is allowed only when chosen. Judge the turn by the tip of the nose, not by the centre of the
head. The face never slides across a head that stays still. The nose dips during the turn, and the head ends a little past its
target before it settles.

### ARC7. Out on one arc, back on another
stages: blocking, passes

A gesture that goes out and comes back returns on a different curve, so its path forms a loop. Elbows and wrists
draw small figure eights. In a walk the wrist traces a flattened eight; read it from the top and the side. A gesture that ends in a hold loops
through a small eight as it arrives, never stopping dead on its last key.

An eight is made of two layered channels, never one drawn line: in each cycle the part crosses sideways once and
rises and falls twice. A fast or complex action is a chain of such loops: keep a small loop at each change of direction of the
wrist, because a sharp reversal there reads as robotic.

### ARC8. Gestures dip below the straight line
stages: blocking, passes

On a point, a reach or a wave, the wrist travels down and then up between its keys, below the straight line that
joins them. When a glance leads into a point, the hand scoops low beneath the torso before it rises into the point.

### ARC9. Track each arc where its energy starts
stages: blocking, passes, checks

Follow the hips for the body and the ankle for the foot, not the toe or the heel. On a free arm swing the elbow leads
the swing back and the wrist leads the swing forward, while the hand drags behind. When the arm is driven (a slap, a hit, a raise), the elbow keeps the lead in both directions and the forearm only
whips through at the end. Arcs nest: the elbow draws a smaller copy of
the wrist's curve and the shoulder a smaller one again, in the same direction. The shoulder never stays locked.

### ARC10. A mass that stops keeps moving on one small arc
stages: blocking, passes

When the base stops (planted feet, a wheel), the mass above it carries on forward and down, swings back and up a
little past rest, then settles. That overshoot is one small curve with a breakdown on it. Move the mass and keep the
base still. The swing comes from a restoring force; nothing is added that the body could not produce.

### ARC11. A change of direction needs a cause
stages: plan, blocking, passes

Bending a route takes a push from the ground. Plant each foot outside the moving mass, so that the foot both checks
the old heading and sends the mass round: a walker turning a right angle to its right is steered by its left leg.
Tip the hips and the trunk in toward the centre of the bend for as long as the bend lasts. Raise the speed and both
the radius and the inward tilt grow, and the route still curves without a corner.

Before the new heading takes over, the old one has to be spent. Give that a few frames of lean, skid or slide, and
give a heavier body more frames and more steps of braking before it can stop or turn. Unless such a cause is on
screen, a travelling character or heavy object keeps an even spacing and a fixed heading: no surge, no stall, no
change of direction.

The intent of a turn shows one frame after the decision, as a lean and a look, even when the body then sweeps a wide
arc at speed. A cycle that turns keeps leaning inward for the whole curve, and each change of direction shows a weight
shift.

### ARC12. Split a strike's path at the moment of delivery
stages: plan, blocking, passes

A strike keyed as one straight line from start to end is wrong, and so is one that rounds softly through the impact.
Shape the path in three stretches instead, divided where the force is passed on: a curved approach out of the wind-up,
a delivery stretch that may run straight, and a spiral as the part twists away after the contact or the release.

### ARC13. The line of action and the path of action are separate lines
stages: plan, blocking, passes

Even a pose whose line of action is straight should move along a curving path. A straight, upright shape crossing the
screen on a straight path tends to strobe: tilt the shape and curve its path.

### ARC14. Step through the frames and trace the arcs
stages: passes, checks, self_review

Playback hides arc faults. Scrub one frame at a time in both directions and mark one point every frame on the screen
path.
First pick the point with the largest or most important arc in this camera, then trace the nose, the wrists, the
elbows, the knees, the ankles and the hips. Judge arcs on the screen path, never in the curve editor. Number the keys
in one colour and the breakdowns in another. One frame off the curve, or one gap out of order along it, is a hitch.

The curve editor answers other questions: where a part starts, stops, speeds up or reverses. Every peak or valley in a
curve shows the part turning back on screen, and each turn must have a reason.

### ARC15. Fix an arc by drawing its target
stages: passes

Where a traced point bumps or runs flat, first mark the spot it should reach, then adjust whichever key or breakdown
is closest until the point lands on the mark. If no existing key can reach it, add one breakdown on the curve. Never correct an arc with a
run of keys on every frame. If the arc can only be made by breaking the character's balance, the pose is wrong: go back
and change the pose.

### ARC16. Spend arc work where the eye goes
stages: passes, self_review

Viewers follow the hands and the head, so the arcs of the hands, the path of the nose and the figure eights of elbow
and wrist buy the most smoothness. This ranks the work; it never excuses a body that loses its balance.

### ARC17. Arcs are planned, carried by the poses, then refined
stages: plan, blocking, passes, self_review

The plan sheet shows the intended arc of each main part. Each key pose already sits on its planned curve; a key far
off its path is fixed in the pose itself. Breakdowns set the arcs. Small decorative loops and curls are left for the late passes. When a shot looks weak, check the posing first, then the timing, then the arcs. No shot is finished before one full pass over its arcs.

### ARC18. Clean arcs everywhere can look weightless
stages: passes, self_review

A heavy part may break its arc after an impact, for example a head that drops hard after a punch, to show weight.
Write the break down as a choice; an unexplained corner is still a fault.

### ARC19. Props, loose parts and tips have paths of their own
stages: blocking, passes, checks

A blade tip, a tail, hair or a cape each draw their own curve: the weapon one large continuous loop through each
strike, the loose parts smaller loops of their own. Props are where an arc can be exaggerated most safely. Trace the
tip of every trailing part: its path is smooth, repeats its pattern, and shrinks with each bounce. On smear frames,
track the solid object, never the edge of the smear. Trace a held tool's tip together with the wrist; its arc is larger
and grows out of the wrist's.

### ARC20. Ease into the end of an arc
stages: blocking, passes

The spacing tightens over the last few frames of a curve, typically four or five, so the part settles into its end
pose instead of hitting it.

### ARC21. Space moves into depth in the world, not on the screen
stages: blocking, passes

Moves toward or away from the camera, and turns viewed side on, get their spacing in world space or from the top
view: even steps in depth, or even angles for a turn. Seen through the camera, the frames then bunch toward the far end and at
the edges of a turn. That bunching is correct; halving the screen distance is not.

### ARC22. Arc size follows timing and style
stages: plan, passes

Realistic work keeps its arcs, only smaller. Stylised work pushes the curves of real motion a little further than
life. A faster move and a slower move between the same poses need different curves; decide the size with the timing.

Foot arcs follow the same logic. The heavier the walk, the smaller and lower the foot's arc; a light or happy walk swings the
foot higher, and running enlarges the arcs again. A small arc still lifts the foot clearly and pushes off with intent; it never becomes a shuffle.
Each character gets one arc amount, set once: full for anything alive, toned down for a robotic style but never zero.

### ARC23. Trace the true pivot, and fix the root first
stages: passes, checks, self_review

Trace a real joint or the true pivot of a part, never the base of a control's shape, which can sit far from the bone.
Where a part has no joint at the point that matters, such as the head, attach a marker inside it and trace that. A
body that rotates in the air turns about its centre of mass, and that point shifts inside the body whenever the shape
changes: near the hips while the body is open, at the middle of the ball when it is tucked at the apex, and near the
back of the spine by the time it lands. Place that moving pivot on every key, then read each arc relative to it; a
vertical flip is read from the side, in a view without perspective. If no joint lies at the centre of mass, its path
is judged by eye.

Repair the root's arc before the spine controls above it, then mend the breakdowns that the root change disturbed.
Trace again after every change until the shape holds.

### ARC24. Read each part's real path; not every arc is a C
stages: references, study, plan

The main masses, such as a thrown ball, a head going back or a kicking leg, travel on C-shaped curves. Where the
motion reverses, the path turns into an S: a trailing wrist draws a long S, and so does a vaulting body. A throwing
hand follows a wave: down, up, then a long and nearly flat stretch. Multiple-exposure photographs of athletes show
these paths plainly; trace the wrist or the end of the tool in them. Copy the shape the reference shows, and never
bend every path into a C.

### ARC25. Balance makes small arcs; name each arc's cause
stages: understanding, passes

A character holding its balance keeps drawing small paths. Seen from the top, the hips turn on a near circle, and the
wrists and shoulders answer with small closed loops. When a step takes the weight, the foot gets its arc and the hip
height dips under it on a low curve. Before pushing any arc larger, name what produces it: balance, weight or momentum.
The cause decides whether the arc may grow, and by how much.
