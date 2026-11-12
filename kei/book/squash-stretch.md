# Squash and stretch

kind: principle

A shape that flattens on impact and lengthens with speed shows weight, softness and force. These rules cover how much
a shape may change, when it changes, how a body does it through its pose, and what a realistic rig and an engine allow.

### SQS1. Change the shape, never the amount of it
stages: passes, checks

Squash and stretch alters proportions while the volume stays fixed. A shape that grows longer also grows thinner; a
shape pressed flatter also spreads wider. Seen from the side, height times width stays the same. In 3D, scale the
long axis by s and each cross axis by 1 over the square root of s, so the side-on area changes by the square root of s,
which is correct.

When the rig or the software lets volume drift, scale the other axes by hand to restore it. A stretch that keeps its old width looks
as if it gained mass, and a squash that does not spread looks as if it lost some. Twisting a soft mass keeps its volume
too.

### SQS2. The material sets the amount
stages: understanding, plan, passes

A coin, a metal ball or a golf ball seen at normal speed keeps its shape: correct spacing alone sells the bounce. Soft
and fleshy things deform more. Typical ground squash, as a fraction of rest height: a bowling ball keeps about 0.93,
a soft beach ball drops to about 0.75, and a rubber ball to about 0.65 while its width grows to about 1.54. Typical stretch caps: about 1.04 for a
bowling ball and 1.3 for rubber. A rigid part of any object keeps its shape exactly. Too much squash everywhere turns
every material into rubber.

### SQS4. A stretch limit is a declared style value, not a fix for anatomy
stages: plan, passes, checks

How far limbs and spine may lengthen belongs to the clip, written in the plan, and never hard-coded. Typical caps
for a moderately pushed clip: 1.15 on the legs, 1.20 on the arms and 1.10 on the spine. Every stretch returns to 1 during a hold. A broad film
style may lengthen fast drawings near a contact to about 1.4.

A stretch never replaces a move the body could make. Lengthening arms to touch a target, or legs that bend like hoses with no
knee, are faults: the body should lean, step or turn to get there. In a realistic shot no limb or spine is lengthened
in the first pass; stretch is tried only after the anatomical pose has failed, and any reach that falls short is
reported, not hidden.

### SQS18. A flat side gives a shape a direction
stages: blocking, passes

A perfectly round shape points nowhere. Flattening one side of it makes it face somewhere. Use this to aim a head, a
fist or a soft prop.

### SQS5. A ball stretches only when it moves fast for its size
stages: blocking, passes, checks

In the air a ball is round. It lengthens only when its speed, measured in its own diameters per frame, is high. A
usable rule: stretch = 1 + 0.5 x (speed - 0.6), clamped between 1 and the material cap. On a one metre drop this
affects just two or three frames ahead of the impact and about two following it, peaking near 1.26 for rubber;
the middle drawings of the fall stay round. Stretch exists to make a fast move easier for the eye to follow.

A stretch that looks too long is often a spacing fault. Move the drawing along its path first, then judge the shape
again.

### SQS6. Stretch lies along the path
stages: blocking, passes

The long axis of a stretch follows the direction of travel. On a jump it tilts with the arc instead of standing
upright. A stretch never pushes through the ground. Keep the shape as one channel aligned with the path, not as
separate vertical and horizontal scales: split channels let the axis flip in a single frame and hide a pop that only
shows once the curves are converted to splines.

### SQS7. A ball is round at the top unless the style flattens it
stages: blocking, passes

A ball hanging at its apex stays round by default. A styled bounce may instead let the upper side of the ball lose
speed before the lower side, so the lower side closes in and the apex drawing comes out slightly flattened, by about a
tenth of its height (8 to 11 %), its area unchanged. Pick one of these two and record it in the plan.

### SQS9. Squash grows with the speed of impact
stages: blocking, passes, checks

A soft landing compresses a little and a hard hit compresses a lot. Each later, smaller bounce squashes less than the
one before; small bounces that squash as deeply as the first look like jelly. A landing usually squashes far less
than the antic squash that launched the same jump.

### SQS8. The contact drawing is stretched; the squash comes on the next frame
stages: blocking, passes, checks

On the frame a soft ball arrives, it is drawn long along the line it came in on, about two fifths longer than its
width, touching the ground with its tip only; no drawing of the fall is more stretched. The squash, wide and flat,
comes on the frame after. A contact frame showing an almost round ball already pushed into the ground is a fault. A
rigid ball gets one round contact drawing.

On the way back up, a passive ball has no contact drawing of its own: the squash is its first frame leaving, and it
then stretches as it goes, top first. The next drawing slightly overlaps the squash. A departing stretch is added only
when the gap to the next drawing is large compared with the ball, and it stays modest, or the ball looks limp.

### SQS11. A self-propelled launch is a squash that feeds a stretch
stages: plan, blocking, passes

A body that launches itself always compresses before it rises: the crouch is both the anticipation and the
squash, and it leans away from the coming jump. On the very next frame after the deepest squash comes the leap frame:
fully stretched, leaning along the jump, its base still touching. When a lifeless object such as a kettle or a cushion
is made to hop, the whole object does the work: it squashes, stretches as it leaves, stretches again as it touches
down, squashes after the touch, and snaps back to its model shape.

Typical values at 30 fps for a lively ball: about five frames from the start of the squash to take-off; the last
ground frame near 1.5 long; the greatest stretch, near 1.85 by 0.66, on the first frame in the air; round again
after about nine frames. A creature's antic squash held about one second reads clearly. In general, a hop's rise and
its fall each last the square root of 2h over g, where h is the hop height and g the project's gravity value, and each
short ground span around the flight lasts about a twelfth of a second. For a typical hop at 24 fps, that means: each
ground span, from the antic squash to the launch and from the touch to the landing squash, takes 2 frames; the flight
takes 8 frames up and the same 8 down; and the return from the landing squash to the normal shape takes one frame more
than a ground span, so 3.

### SQS13. A landing squashes after the touch, and holds
stages: blocking, passes

The moment of contact falls between two frames. The frame before it shows the legs straight or nearly straight; the
frame after it shows the compression. A straight leg never appears over a flat foot. The body hits and squashes while
loose parts are still travelling.

After the contact the body overshoots into a squash and stays there while the character gathers itself, a few frames
longer than feels comfortable, drifting slowly upward. Then a stretch recoil carries it into the rise. When a creature lands briefly, treat it as a single held squash: keys go on the touch, the squash and the deepest
loaded gather, and the tangents supply the absorb in between.

### SQS10. Remove a frame to make an impact land harder
stages: passes

A hit lands harder when one frame just touches before the flattening, and harder still when the frame before the touch
is removed, the frame ahead of the gap is eased back a little, and the touching frame is stretched: the eye senses the
jump across the missing frame without ever seeing that frame. Whatever is struck that hard deforms at the instant of
contact and gets its shape back within very few frames. Save the missing frame for the few hits that must land
hardest; spent on every hit, it stops standing out.

### SQS14. On a body, the pose is the squash and the stretch
stages: plan, blocking, passes

A character squashes by folding and stretches by extending, with no scaling. A compact crouch with every limb folded
is a squash; a push with the hip, knee, heel and toe all extended is a stretch. Bent joints read as squash and straight
joints as stretch. In a walk the down position is the squash and the up position the stretch: a heavy body sinks lower
on the down, a light one rises higher on the up over a straight support leg.

On an extreme, reach through a full extension of the legs, arms and spine rather than lifting a foot that should stay
planted.

### SQS15. Pose the squash and the stretch of an action as a pair
stages: plan, blocking

For each action, design its compressed extreme and its extended extreme at the same time, and exaggerate one against
the other while timing is still untouched. Flip between them at a small size: if the silhouette barely changes, both poses are weak. Anticipation and
squash and stretch are separate tools that often coincide; the pairing can also run the other way, with a stretched
wind-up and a squashed hit.

Push the base pose first and add any global squash or stretch control last. Compare against the unpushed version to
see whether the push helped, and judge it through the shot camera.

### SQS16. Let parts take opposite states
stages: blocking, passes

In one pose some parts may be compressed while others extend, such as a straight stretched leg under a bunched body
with reaching arms. The pattern across the parts is the attitude: a lean, a contrapposto, a drunken slump. In a squash
pose keep the part that carries the load as one long, unbent line; against the compressed masses it shows the
tension. At the very point of contact, such as fingertips on a surface, a small squash returns.

Compress a torso by folding it, one side short and the other long, never by shrinking it evenly, which reads as lost
mass. The hips widen slightly. One mass can hold both states at once.

### SQS17. Squash where weight presses and where muscle works
stages: passes, checks

A mass compresses where it presses on something and where muscle contracts: a working thigh bulges on top while its
stretched side stays straighter. Bone limits the change. Cheeks and jaw can squash a great deal; the top of the skull,
the cheekbones and the hands very little, and squash through bone reads as crushing. When two features move toward
each other, the tissue between them bulges; when they move apart, it thins.

### SQS22. Each part reaches its squash in turn
stages: blocking, passes, checks

The one-joint-at-a-time order of a body decides when each part arrives at its squash or stretch; the rules in this
topic decide the shape it takes. On a landing the full squash pose settles a few frames after the contact, with the
head arriving last. When it takes off, the head is again the final part to stretch.

### SQS19. A quadruped squashes at the ends of its legs
stages: understanding, blocking, passes

The spine and pelvis twist and tilt, and each leg keeps the length of its bones, never bending like a hose. Weight
lands on the legs at their ends and joints: the hind leg gives at the haunch; the front leg gives in three places, the
toes, the wrist and the shoulder blade. That blade is what carries the front leg. It lies ahead of the ribcage, free to
slide over it, and the leg moves forward and up with it rather than hinging on an elbow held in place; when the front
legs take a heavy landing, the elbow may rise above the line of the back. At the push-off a leg straightens almost
fully, so a leg that stays bent on every frame is a fault.

### SQS20. Anatomy first; a squash control is the last layer and stays small
stages: blocking, passes, checks

Get fluid motion from joints bending one after another, not from scaling. A squash or stretch belongs only where the
centre of mass really loads or releases; anywhere else it is a fault. On a character it should be felt rather than
seen: for example the chest compressing a little in the low point of a fold, a flat tangent where the squash is
deepest, and a release key kept low so the body does not spring upward. Add a slight head squash during the antic and
a slight head stretch during the drive, with the eyes following, plus face accents that echo the body; nothing more.

Stretching the body moves the hip joint and so reduces how far the legs reach: recheck leg extension afterwards.

### SQS21. On a rig with a squash control, key it on the poses, then offset it
stages: passes

Because a squash control changes the visual arc of the hips, start it in the first refining pass: squash on the low
pose, stretch on the high pose, the other axis keyed opposite to hold the volume, each value a little different from
the last (for example 0.95 squash on a simple dip, or 1.1 stretch against 0.9). Leave the vertical curve of the root a
little open until the offsets are in. In polish, offset the curves: the stretch reaches its peak one frame ahead of the
root's lowest point, the squash comes in faster than the stretch went out, then settles, with the shoulders lagging.

When the feet are locked and the hips rise and fall, key the leg stretch opposite the hips, on those same frames, so the
knees hold their bend, with small pops at most. On realistic rigs leg stretch is off by default and is declared when used.

### SQS25. One stretched frame can carry a move too fast to see
stages: passes, self_review

When a move covers too much ground for the eye to follow across two clean frames, such as the fastest point of a push
or the start of a fall, one frame elongated along the path may stand in for the blur and go past the clip's stretch
limit. It plays on ones, it is declared on the plan, it sits on a smooth curve, and it is never placed on a blend
frame. At speed it should feel snappier; paused, it looks odd, which is correct. In the check it shows as a one-frame
peak in a limb length or stretch channel. Spacing remains the normal way to show speed and impact: no speed lines,
sparks or decorative smears are added.

A sudden panic may cut the anticipation and the in-betweens and go straight into the extreme, but only when a
convincing stretch bridges the jump and several frames of resolve follow so the audience can read the result.

### SQS24. An extreme distortion is a flash, never a hold
stages: blocking, passes, checks

A take or a hit accent starts from the normal pose, distorts for at most a tenth of a second (one or two frames at 24
fps, up to three at 30, and a single frame is always allowed), then returns quickly to normal proportions while the
attitude of the take stays. Anything stretched for longer is a pose rather than a snap and needs a written reason. At
the accent, the loose parts (a hat, a coat, hair, ears) are flung the same way as the take before they follow
through. Volume holds throughout, and at each pause the character's proportions, height included, are compared with
the model.

On the stretch key leading into a take, the face may already show its final expression while the spine reverses one
more time and the trailing parts, such as the hands, swing the opposite way.

### SQS23. Every distortion has a planned exit
stages: plan, passes, checks

Any departure from the model, whether a squash, a stretch, a smear or a cheat, is made on purpose and is followed by a
way back to the designed proportions and volume. Plan the way back with frames of its own, as carefully as the
distortion itself. After each one, look whether the shape truly recovers or is left slightly long or slightly flat. On
a 3D rig, write a frame limit after the extreme; by that frame all scale channels read 1 again and all stretching
bones are back at rest length.

An action that could never happen still follows rules of its own: a morph is steered by the body's volume and its
pattern lines, and the character's personality comes through it intact.

### SQS3. The design sets the register, and the register holds for the whole shot
stages: brief, understanding, plan

Read from the character design whether its motion is realistic or styled, and how far each character may change
shape. A design built to look dignified or threatening holds its outline and proportions even at the height of an
emotion; a loose, comic design can squash, stretch and distort a long way. One character never mixes the two
registers. Anticipation, squash and stretch, overlap and follow-through rise and fall together, so a single
exaggeration level governs the shot. A hand-keyed clip that plays among motion capture takes the register of that set.

### SQS26. Check that the engine carries scale before relying on it
stages: rig, plan, deliver

Squash and stretch on a 3D character needs bone scale, and many engines and export formats drop it. A format with no
scale channel loses every scaled frame; scale keys must travel in a format that holds them, and a stretched pose can
still arrive unstretched on a target skeleton. Test the export on the target engine first. In a game clip, use scale
only where the engine is known to keep it, and get the same read from the pose wherever possible.

### SQS27. Sharp shape changes at contacts are declared, not flagged
stages: checks, self_review

A ball or creature changes shape in a single frame at take-off and at landing: the gather, the leap and the first air
frame; the contact and the squash. Declare those corners per channel before running a smoothness check, or each one
reads as a jerk spike. Unwrap an angle channel before differencing it. A ball or a tail has no fixed jerk limit; measure
the shot against its own earlier pass instead.
