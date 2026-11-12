/* rig_golden.js: writes the golden fixtures for kei/rig.py and kei/sample.py from the kit's own rig.
   Run by hand, once, when the kit's rig changes:
     node tools/rig_golden.js <path to animator-kit>
   It loads rig4.js and animkit.js from the kit and writes JSON into tests/fixtures/rig/. The tests read the JSON
   and never run node. */
'use strict';
const fs = require('fs');
const path = require('path');

const kit = process.argv[2];
if (!kit) { console.error('usage: node tools/rig_golden.js <path to animator-kit>'); process.exit(1); }
const R4 = require(path.resolve(kit, 'rig4.js'));
const AK = require(path.resolve(kit, 'animkit.js'));
const out = path.resolve(__dirname, '..', 'tests', 'fixtures', 'rig');
fs.mkdirSync(out, { recursive: true });

// the joint names Kei uses: every bone head by its mannequin name, plus the end points
function joints(J) {
  const B = J._bones, o = {};
  for (const n of R4.BONE_LIST) o[n] = B[n].head;
  o.head_top = B.head.tail;
  o.hand_l_tip = B.hand_l.tail; o.hand_r_tip = B.hand_r.tail;
  o.ball_l_tip = B.ball_l.tail; o.ball_r_tip = B.ball_r.tail;
  o.heel_l = J.heL; o.heel_r = J.heR;
  o.sternum = J.sternum; o.nose = J.nose;
  o.com = AK.com(J);
  return o;
}
const tails = (J) => { const o = {}; for (const n of R4.BONE_LIST) o[n] = J._bones[n].tail; return o; };
// a full pose: one key through the rig's own normalizeKeys (missing channels take the default stand)
function full(partial) { const k = R4.normalizeKeys({ keys: [Object.assign({ f: 0 }, partial)] })[0]; delete k.f; delete k.name; delete k.tangent; return k; }

const POSES = {
  rest: {},
  yaw_pelvis: { yaw: 1.2, pelvis: [0.3, -0.2] },
  spine_curl: { spine: [0.8, 0.4, 0.6], spine3: [0.3, -0.2, 0.1], spine5: [-0.2, 0.1, 0.3] },
  spine_arch: { spine: [-0.7, -0.3, -0.5], spine1: [0.1, 0, 0] },
  neck_head: { neck: [0.4, 0.3, 0.5], head: [0.5, -0.3, 0.8], neckS: 1.3 },
  arms: { armL: [2.5, 0.8, 0.6], armR: [-0.8, 1.2, -0.5], elbowL: [1.8, 0.7], elbowR: [0.5, -0.4], handL: [0.9, 0.4], handR: [-0.7, -0.3], clavL: [0.4, 0.3], clavR: [-0.2, 0.5] },
  arm_overhead: { armL: [3.1, 0, 0], armR: [Math.PI / 2, Math.PI / 2, 1.0], elbowL: [0, 0], elbowR: [2.4, 1.2] },
  heel_strike: { rollL: [-0.4, 0, 0.6], rollR: [-0.15, 0, 0.6], footL: [-0.1, 0.08, 0.3, 0, 0] },
  heel_peel: { rollL: [0.35, 0, 0.6], rollR: [0.6, 0, 0.5], footR: [0.12, 0.08, -0.2, 0, 0.3] },
  toe_off: { rollL: [1.2, 0, 0.6], toeL: 0.3, rollR: [0.9, 0.3, 0.4], toeR: -0.4, footR: [0.1, 0.15, -0.25, 0.4, -0.3] },
  bank: { rollL: [0, -0.3, 0.4], rollR: [0.2, 0.35, 0.6], footL: [-0.15, 0.08, 0, -0.3, 0.6] },
  leg_out_of_reach: { root: [0, 1.05, 0], footL: [-0.1, 0.08, 0.9, 0, 0], footR: [0.6, 0.0, -0.5, 0, 0] },
  leg_tight: { root: [0, 0.4, 0], footL: [-0.12, 0.08, 0.05, 0, 0], footR: [0.12, 0.08, -0.05, 0, 0] },
  ankle_front_back: { footL: [-0.1, 0.5, 0.5, 0, 0], footR: [0.1, 0.4, -0.5, 0, 0], kneeL: 0.4, kneeR: -0.3 },
  ankle_under_hip: { root: [0, 0.9, 0], footL: [-0.1, 0.08, 0.0, 0.2, 0.9], footR: [0.1, 0.3, 0.0, -0.5, 0] },
  arm_ik: { ikL: [-0.3, 1.2, 0.4, 1], ikR: [1.5, 1.4, 0.5, 0.6] },
  arm_ik_close: { ikL: [-0.2, 1.3, 0.05, 1], ikR: [0.25, 1.15, 0.2, 0.5], armR: [0.3, 0.2, 0.4] },
  squash_stretch: { root: [0.05, 0.85, 0.1], sq: 0.7, neckS: 0.8, armSL: 1.3, armSR: 0.8, legSL: 1.2, legSR: 0.85, ikR: [0.5, 1.2, 0.5, 1] },
  crouch_turn: { root: [0.2, 0.6, 0.3], yaw: -0.8, spine: [0.6, 0, -0.4], pelvis: [0.4, 0.1], footL: [0, 0.08, 0.5, 0, -0.4], footR: [0.4, 0.08, 0.1, 0, -0.9] },
  // the foot heading blend near vertical toes, and past vertical
  foot_pitch_80: { footL: [-0.1, 0.3, 0.2, 80 * Math.PI / 180, 0], footR: [0.1, 0.3, -0.1, -80 * Math.PI / 180, 0.3] },
  foot_pitch_100: { footL: [-0.1, 0.3, 0.2, 100 * Math.PI / 180, 0], footR: [0.1, 0.3, -0.1, -100 * Math.PI / 180, -0.2] },
  // arm IK with a straight FK elbow: no FK bend plane, the pole falls back to the bend away from the upper arm
  arm_ik_straight_elbow: { elbowL: [0, 0], elbowR: [0, 0.3], ikL: [-0.35, 1.1, 0.35, 1], ikR: [0.4, 1.5, 0.2, 0.7] },
  // the ankle straight above the hip: the knee pole transport meets the antiparallel branch
  ankle_above_hip: { footL: [-0.1, 1.3, 0, 0, 0] },
};
// a knee-flip sweep: the ankle passes under the hip with the foot pitched 0.6 rad
for (let i = -4; i <= 4; i++) {
  const z = i / 10;
  POSES['knee_sweep_pitch_' + (i < 0 ? 'm' : 'p') + Math.abs(i)] = { root: [0, 0.9, 0], footL: [-0.1, 0.3, z, 0.6, 0] };
}
const poses = Object.entries(POSES).map(([name, partial]) => {
  const pose = full(partial), J = R4.skeleton(pose);
  return { name, pose, joints: joints(J), tails: tails(J), over: J._over };
});
// a character's own build: props.proportions overrides the default proportions
{
  const proportions = { thigh: 0.5, calf: 0.48, upperarm: 0.3, spine: [0.12, 0.11, 0.1, 0.1, 0.09] };
  const pose = full({ armL: [1.0, 0.3, 0] }), J = R4.skeleton(pose, { proportions });
  poses.push({ name: 'own_build', pose, proportions, joints: joints(J), tails: tails(J), over: J._over });
}
fs.writeFileSync(path.join(out, 'poses.json'), JSON.stringify({ proportions: R4.PROPORTIONS, default: R4.DEFAULT, bones: R4.BONE_LIST, poses }, null, 1));
console.log('poses.json: ' + poses.length + ' poses');

/* ---------------- keys to frames ---------------- */
const SHOTS = {
  // three keys, channels left out on purpose (they carry over), one flat tangent
  reach: { rig: 'v4', fps: 24, frames: 20, loop: false, keys: [
    { f: 0, root: [0, 0.95, 0], armR: [0.2, 0.1, 0] },
    { f: 8, tangent: 'flat', armR: [1.6, 0.3, 0.2], spine: [0.3, 0, 0.2], elbowR: [0.4] },
    { f: 20, root: [0, 0.9, 0.05], footR: [0.12, 0.08, 0.2], rollR: [-0.2] },
  ] },
  // a travelling walk cycle: the last key is the first plus one cycle of travel
  walk: { rig: 'v4', fps: 24, frames: 24, loop: true, keys: [
    { f: 0, root: [0, 0.96, 0], footL: [-0.1, 0.08, 0.3, 0, 0], footR: [0.1, 0.08, -0.3, 0, 0], rollL: [-0.3, 0, 0.6], rollR: [0.8, 0, 0.6], armL: [-0.4, 0.12, 0], armR: [0.4, 0.12, 0] },
    { f: 6, root: [0, 0.93, 0.32], footL: [-0.1, 0.08, 0.3, 0, 0], footR: [0.1, 0.2, 0.25, 0, 0], rollL: [0, 0, 0.6], rollR: [0, 0, 0.6] },
    { f: 12, root: [0, 0.96, 0.6], footL: [-0.1, 0.08, 0.3, 0, 0], footR: [0.1, 0.08, 0.9, 0, 0], rollL: [0.8, 0, 0.6], rollR: [-0.3, 0, 0.6], armL: [0.4, 0.12, 0], armR: [-0.4, 0.12, 0] },
    { f: 18, root: [0, 0.93, 0.92], footL: [-0.1, 0.2, 0.85, 0, 0], footR: [0.1, 0.08, 0.9, 0, 0], rollL: [0, 0, 0.6], rollR: [0, 0, 0.6] },
    { f: 24, root: [0, 0.96, 1.2], footL: [-0.1, 0.08, 1.5, 0, 0], footR: [0.1, 0.08, 0.9, 0, 0], rollL: [-0.3, 0, 0.6], rollR: [0.8, 0, 0.6], armL: [-0.4, 0.12, 0], armR: [0.4, 0.12, 0] },
  ] },
  // a loop in place (no travel), keys out of order on purpose
  sway: { rig: 'v4', fps: 30, frames: 30, loop: true, keys: [
    { f: 15, spine: [0.1, -0.3, 0], yaw: -0.2 },
    { f: 0, spine: [0.1, 0.3, 0], yaw: 0.2 },
    { f: 30, spine: [0.1, 0.3, 0], yaw: 0.2 },
  ] },
  // a loop of two keys: too few for wrapped neighbours, so the end tangents fall back
  two_key_loop: { rig: 'v4', fps: 24, frames: 16, loop: true, keys: [
    { f: 0, root: [0, 0.95, 0], armR: [0.6, 0.1, 0] },
    { f: 16, root: [0, 0.95, 0.4], armR: [-0.3, 0.1, 0] },
  ] },
  // a travelling loop with arm IK on: the IK targets travel with the root
  travel_ik: { rig: 'v4', fps: 24, frames: 16, loop: true, keys: [
    { f: 0, root: [0, 0.95, 0], ikR: [0.3, 1.1, 0.35, 0.8], footL: [-0.1, 0.08, 0.2, 0, 0], footR: [0.1, 0.08, -0.2, 0, 0] },
    { f: 8, root: [0, 0.92, 0.4], ikR: [0.35, 1.2, 0.8, 0.6], footL: [-0.1, 0.08, 0.2, 0, 0], footR: [0.1, 0.08, 0.6, 0, 0] },
    { f: 16, root: [0, 0.95, 0.8], ikR: [0.3, 1.1, 1.15, 0.8], footL: [-0.1, 0.08, 1.0, 0, 0], footR: [0.1, 0.08, 0.6, 0, 0] },
  ] },
};
const cut = (fr) => fr.map((x) => ({ f: x.f, pose: x.pose, joints: joints(x.J) }));
const shots = Object.entries(SHOTS).map(([name, shot]) => {
  const at = AK.sampler(shot, 'spline');
  const between = [0.5, 3.25, 7.9, 13.6, shot.frames - 0.2, shot.frames + 2.5, -1.5].map((f) => ({ f, pose: at(f) }));
  return { name, shot, keys: AK.normalizeKeys(shot), between,
    step: cut(AK.bake(shot, 'step')), linear: cut(AK.bake(shot, 'linear')), spline: cut(AK.bake(shot, 'spline')),
    continuous: cut(AK.bakeContinuous(shot)) };
});
fs.writeFileSync(path.join(out, 'shots.json'), JSON.stringify({ shots }, null, 1));
console.log('shots.json: ' + shots.length + ' shots');
