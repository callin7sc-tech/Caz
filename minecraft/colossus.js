import { world, system, EntityDamageCause, GameMode } from '@minecraft/server';

// Stable Script API 2.0.0. Timings are shared with the resource-pack animations.
export const ROBOT = 'gc:robot_colossus';
export const CONFIG = Object.freeze({
  range: 28, laserDamage: 16, stompDamage: 24, stompRadius: 4,
  laserHitTick: 20, stompHitTick: 16, laserDuration: 40, stompDuration: 32,
  laserCooldown: 70, stompCooldown: 54, turnStep: 30, thinkInterval: 10,
});
const dimensions = ['overworld', 'nether', 'the_end'];
const states = new Map();
let lastWarning = -200;
const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
const add = (a, b) => ({ x: a.x + b.x, y: a.y + b.y, z: a.z + b.z });
const scale = (v, n) => ({ x: v.x * n, y: v.y * n, z: v.z * n });
const length = v => Math.hypot(v.x, v.y, v.z);
const unit = v => scale(v, 1 / Math.max(length(v), 0.0001));
const radians = n => n * Math.PI / 180;
const wrapAngle = n => ((n + 180) % 360 + 360) % 360 - 180;

function warn(error) {
  if (system.currentTick - lastWarning < 200) return;
  lastWarning = system.currentTick;
  console.warn('[Colosso Robot] ' + error);
}
function set(entity, key, value) {
  if (entity.getProperty(key) !== value) entity.setProperty(key, value);
}
function alive(entity) {
  try { return !!entity?.isValid && (entity.getComponent('minecraft:health')?.currentValue ?? 0) > 0; }
  catch { return false; } // Handles entities invalidated between query and update.
}
export function isTarget(entity) {
  if (!alive(entity) || entity.typeId === ROBOT) return false;
  if (entity.typeId === 'minecraft:player') {
    const mode = entity.getGameMode();
    return mode !== GameMode.Creative && mode !== GameMode.Spectator;
  }
  const families = entity.getComponent('minecraft:type_family');
  return !!families && ['monster', 'goblin_caravan', 'goblin'].some(f => families.hasTypeFamily(f));
}
function targetPoint(entity) {
  const head = entity.getHeadLocation();
  return { x: head.x, y: Math.max(entity.location.y + 0.2, head.y - 0.2), z: head.z };
}
function wallDistance(dimension, origin, direction, maxDistance) {
  const hit = dimension.getBlockFromRay(origin, direction, {
    maxDistance, includeLiquidBlocks: false, includePassableBlocks: false,
  });
  return hit ? length(sub(add(hit.block.location, hit.faceLocation), origin)) : maxDistance;
}
export function visible(dimension, origin, point) {
  const delta = sub(point, origin);
  const distance = length(delta);
  return distance < 0.1 || wallDistance(dimension, origin, unit(delta), distance) >= distance - 0.05;
}
function sound(robot, name, pitch = 1) {
  try { robot.dimension.playSound(name, robot.location, { volume: 1.5, pitch }); }
  catch (error) { warn(error); }
}
function particle(dimension, name, position) {
  // Unloaded chunks or optional cosmetics must never interrupt damage or recovery.
  try { dimension.spawnParticle(name, position); } catch (error) { warn(error); }
}
export function eyeOrigins(robot, yaw, pitch) {
  const y = radians(yaw), p = radians(pitch);
  const forward = { x: -Math.sin(y), y: 0, z: Math.cos(y) };
  const side = { x: Math.cos(y), y: 0, z: Math.sin(y) };
  // Same head pivot and lens centers as robot_colossus.geo.json (16 units/block).
  const height = 7 + 0.3125 * Math.cos(p) - 0.8125 * Math.sin(p);
  const depth = 0.3125 * Math.sin(p) + 0.8125 * Math.cos(p);
  const center = add(robot.location, add(scale(forward, depth), { x: 0, y: height, z: 0 }));
  return [-0.375, 0.375].map(offset => add(center, scale(side, offset)));
}
function aim(robot, state, target) {
  const point = targetPoint(target);
  const delta = sub(point, add(robot.location, { x: 0, y: 7, z: 0 }));
  const desired = Math.atan2(-delta.x, delta.z) * 180 / Math.PI;
  const turn = wrapAngle(desired - state.yaw);
  state.yaw = wrapAngle(state.yaw + Math.max(-CONFIG.turnStep, Math.min(CONFIG.turnStep, turn)));
  state.pitch = state.action === 'stomp' ? 0 : Math.max(-70, Math.min(75,
    -Math.atan2(delta.y, Math.hypot(delta.x, delta.z)) * 180 / Math.PI));
  state.point = point;
  robot.setRotation({ x: 0, y: state.yaw });
  set(robot, 'gc:aim_yaw', state.yaw);
  set(robot, 'gc:aim_pitch', state.pitch);
  return Math.abs(turn) <= CONFIG.turnStep;
}
export function fireLaser(robot, state) {
  const damaged = new Set();
  for (const origin of eyeOrigins(robot, state.yaw, state.pitch)) {
    const direction = unit(sub(state.point, origin));
    let distance = wallDistance(robot.dimension, origin, direction, CONFIG.range);
    const hits = robot.dimension.getEntitiesFromRay(origin, direction, {
      maxDistance: distance, ignoreBlockCollision: false,
      includeLiquidBlocks: false, includePassableBlocks: false, excludeTypes: [ROBOT],
    }).sort((a, b) => a.distance - b.distance);
    // The first living body intercepts the beam. Passive mobs are shields, not targets.
    const hit = hits.find(h => alive(h.entity) && h.distance <= distance);
    if (hit) {
      distance = hit.distance;
      if (isTarget(hit.entity) && !damaged.has(hit.entity.id)) {
        damaged.add(hit.entity.id);
        try {
          hit.entity.applyDamage(CONFIG.laserDamage, {
            cause: EntityDamageCause.entityAttack, damagingEntity: robot,
          });
        } catch (error) { warn(error); }
      }
    }
    // One short-lived, continuous-looking violet beam from EACH eye; <= 190 points.
    const count = Math.ceil(distance / 0.3);
    for (let i = 0; i <= count; i++) {
      particle(robot.dimension, 'gc:colossus_laser', add(origin, scale(direction, distance * i / Math.max(1, count))));
    }
    particle(robot.dimension, 'gc:colossus_spark', add(origin, scale(direction, distance)));
  }
  sound(robot, 'mob.guardian.attack', 0.65);
}
export function footPosition(robot, yaw) {
  const r = radians(yaw);
  // Right foot center: geometry X=-16, Z=-6; Bedrock X/Z flip into world space.
  return add(robot.location, { x: Math.cos(r) - Math.sin(r) * 0.375, y: 0.25, z: Math.sin(r) + Math.cos(r) * 0.375 });
}
export function stomp(robot, state) {
  const center = footPosition(robot, state.yaw);
  // maxDistance is 3D, broaden query before applying the horizontal/height limits.
  for (const victim of robot.dimension.getEntities({ location: center, maxDistance: 6 })) {
    if (!isTarget(victim)) continue;
    const delta = sub(victim.location, center);
    if (Math.hypot(delta.x, delta.z) > CONFIG.stompRadius || Math.abs(delta.y) > 2.5) continue;
    if (!visible(robot.dimension, add(center, { x: 0, y: 0.4, z: 0 }), targetPoint(victim))) continue;
    try {
      const applied = victim.applyDamage(CONFIG.stompDamage, { cause: EntityDamageCause.entityAttack, damagingEntity: robot });
      if (applied) {
        const d = Math.max(Math.hypot(delta.x, delta.z), 0.1);
        victim.applyKnockback({ x: delta.x / d * 1.5, z: delta.z / d * 1.5 }, 0.55);
      }
    } catch (error) { warn(error); }
  }
  // Concentric ground rings, no explosions, fire, block destruction or command injection.
  for (const radius of [1.3, 2.6, CONFIG.stompRadius]) {
    for (let i = 0; i < 24; i++) {
      const a = i * Math.PI / 12;
      particle(robot.dimension, 'gc:colossus_spark', add(center, { x: Math.cos(a) * radius, y: 0, z: Math.sin(a) * radius }));
    }
  }
  sound(robot, 'random.explode', 0.55);
}
function recover(robot, state, now) {
  state.action = 'idle';
  state.ready = now + 12;
  state.nextThink = state.ready;
  state.aligning = false;
  set(robot, 'gc:action', 'idle');
  set(robot, 'gc:attack_tick', 0);
  set(robot, 'gc:aim_pitch', 0);
  robot.triggerEvent('gc:colossus_resume');
}
function chooseTarget(robot, previous) {
  const origin = add(robot.location, { x: 0, y: 7, z: 0 });
  const usable = entity => {
    try {
      return isTarget(entity) && entity.dimension.id === robot.dimension.id &&
        length(sub(entity.location, robot.location)) <= CONFIG.range &&
        visible(robot.dimension, origin, targetPoint(entity));
    } catch { return false; }
  };
  // Retain a valid target instead of twitching between nearby players/mobs.
  if (usable(previous)) return previous;
  return robot.dimension.getEntities({ location: robot.location, maxDistance: CONFIG.range })
    .filter(isTarget)
    .sort((a, b) => length(sub(a.location, robot.location)) - length(sub(b.location, robot.location)))
    .find(usable);
}
function begin(robot, state, action, target, now) {
  state.action = action;
  state.start = now;
  state.target = target;
  state.hit = false;
  state.turnTicks = 0;
  state.yaw = wrapAngle(robot.getRotation().y);
  state.aligning = !aim(robot, state, target);
  set(robot, 'gc:attack_tick', 0);
  set(robot, 'gc:action', action);
  robot.triggerEvent('gc:colossus_freeze');
  if (action === 'laser') {
    state.nextLaser = now + CONFIG.laserCooldown;
    sound(robot, 'beacon.activate', 0.6);
  } else {
    state.nextStomp = now + CONFIG.stompCooldown;
    sound(robot, 'mob.irongolem.walk', 0.6);
  }
}
export function updateRobot(robot, now) {
  let state = states.get(robot.id);
  if (!state) {
    state = { action: 'idle', nextLaser: now + 20, nextStomp: now + 20, ready: now + 20 };
    states.set(robot.id, state);
    // Recover persisted component groups/properties after reload or chunk re-entry.
    recover(robot, state, now);
    state.ready = state.nextThink = now + 20;
    return;
  }
  if (state.action !== 'idle') {
    const age = now - state.start;
    const laser = state.action === 'laser';
    if (!state.hit && (!isTarget(state.target) || state.target.dimension.id !== robot.dimension.id ||
        length(sub(state.target.location, robot.location)) > CONFIG.range + 2)) {
      recover(robot, state, now);
      return;
    }
    // Do not replay missed hits after suspension/chunk unloading.
    if (age >= (laser ? CONFIG.laserDuration : CONFIG.stompDuration)) {
      recover(robot, state, now);
      return;
    }
    // Turn on the shortest arc before winding up, rather than snapping 180 degrees.
    if (state.aligning) {
      state.aligning = !aim(robot, state, state.target);
      state.start = now;
      if (state.aligning) state.turnTicks = (state.turnTicks ?? 0) + 2;
      if (state.turnTicks > 40) recover(robot, state, now);
      return;
    }
    robot.setRotation({ x: 0, y: state.yaw });
    const hitTick = laser ? CONFIG.laserHitTick : CONFIG.stompHitTick;
    set(robot, 'gc:attack_tick', Math.min(age, 40));
    if (laser && !state.hit) {
      if (age < hitTick - 4) aim(robot, state, state.target);
      if (age < hitTick && age % 4 === 0) {
        for (const origin of eyeOrigins(robot, state.yaw, state.pitch)) particle(robot.dimension, 'gc:colossus_spark', origin);
      }
    }
    if (!state.hit && age >= hitTick) {
      state.hit = true; // Mark BEFORE effects: an error cannot duplicate damage next tick.
      if (laser) fireLaser(robot, state);
      else if (robot.isOnGround) stomp(robot, state);
    }
    return;
  }
  // runInterval(..., 2) can start on an ODD world tick. Modulo-10 polling
  // starved combat forever in that case; deadlines work for every tick phase.
  if (now < state.ready || now < state.nextThink) return;
  state.nextThink = now + CONFIG.thinkInterval;
  const target = chooseTarget(robot, state.target);
  if (!target) { state.target = undefined; return; }
  state.target = target;
  const direction = sub(target.location, robot.location);
  const yaw = Math.atan2(-direction.x, direction.z) * 180 / Math.PI;
  const delta = sub(target.location, footPosition(robot, yaw));
  const close = robot.isOnGround && Math.hypot(delta.x, delta.z) <= CONFIG.stompRadius && Math.abs(delta.y) < 2.5;
  if (close && now >= state.nextStomp) begin(robot, state, 'stomp', target, now);
  else if (now >= state.nextLaser) begin(robot, state, 'laser', target, now);
  else state.nextThink = Math.min(state.nextThink,
    Math.max(now + 2, close ? Math.min(state.nextStomp, state.nextLaser) : state.nextLaser));
}
export function update() {
  const seen = new Set();
  for (const id of dimensions) {
    try {
      for (const robot of world.getDimension(id).getEntities({ type: ROBOT })) {
        if (!alive(robot)) continue;
        seen.add(robot.id);
        try { updateRobot(robot, system.currentTick); }
        catch (error) {
          warn(error);
          try { recover(robot, states.get(robot.id) ?? {}, system.currentTick); } catch { /* unloaded/dead */ }
        }
      }
    } catch (error) { warn(error); }
  }
  for (const id of states.keys()) if (!seen.has(id)) states.delete(id);
}
system.runInterval(update, 2);
