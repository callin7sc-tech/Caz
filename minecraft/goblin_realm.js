// Goblin Caravan — Regno dei Goblin (custom dimension gc:goblin_realm).
// Requires Bedrock 1.26.30+ and stable @minecraft/server 2.8.0 (DimensionRegistry).
//
// 1. Craft "Mattoni di muschio goblin" with 9 moss blocks (3x3 crafting table).
// 2. Build a frame 4 wide x 5 tall (2x3 opening, corners optional) like a
//    Nether portal, facing X or Z.
// 3. Use flint and steel (or a fire charge) on the frame: the portal lights.
// 4. Stand inside: you travel to the Goblin Realm, a generated world of new
//    blocks, mossbark and glowcap trees, goblin huts and goblins.
import { world, system, BlockPermutation, BlockVolume, GameMode } from '@minecraft/server';

export const REALM = 'gc:goblin_realm';
export const B = {
  frame: 'gc:goblin_moss_bricks', portal: 'gc:goblin_portal',
  grass: 'gc:goblin_grass', soil: 'gc:goblin_soil', stone: 'gc:goblin_stone',
  ore: 'gc:goblin_gold_ore', crystal: 'gc:goblin_crystal',
  mossLog: 'gc:mossbark_log', mossLeaves: 'gc:mossbark_leaves', planks: 'gc:mossbark_planks',
  mossSapling: 'gc:mossbark_sapling', glowStem: 'gc:glowcap_stem', glowCap: 'gc:glowcap_cap',
  glowSprout: 'gc:glowcap_sprout', mushroom: 'gc:goblin_mushroom', fern: 'gc:goblin_fern',
};
export const IGNITERS = ['minecraft:flint_and_steel', 'minecraft:fire_charge'];
const OPENINGS = ['minecraft:air', 'minecraft:fire', 'minecraft:soul_fire', B.portal];
export const WIDTH = 2, HEIGHT = 3;         // opening; the frame is 4 x 5
export const FLOOR_Y = 40, SEA_Y = 61;      // realm bedrock floor and pond level
export const GENERATE_RADIUS = 3;           // chunks generated around players in the realm
export const WAIT_SURVIVAL = 60, WAIT_CREATIVE = 5, COOLDOWN = 80; // ticks

let lastWarning = -200;
function warn(context, error) {
  if (system.currentTick - lastWarning < 100) return;
  lastWarning = system.currentTick;
  console.warn('[Goblin Realm] ' + context + ': ' + error);
}

// ---------------------------------------------------------------- geometry
const AXES = { x: { x: 1, z: 0 }, z: { x: 0, z: 1 } };
export const key = p => `${p.x},${p.y},${p.z}`;
const floorVec = p => ({ x: Math.floor(p.x), y: Math.floor(p.y), z: Math.floor(p.z) });
/** Position relative to a portal origin: along the frame, up, and across (in front/behind). */
export const at = (o, axis, along, up, across = 0) => {
  const a = AXES[axis], c = AXES[axis === 'x' ? 'z' : 'x'];
  return { x: o.x + a.x * along + c.x * across, y: o.y + up, z: o.z + a.z * along + c.z * across };
};
function typeAt(dimension, p) {
  try { return dimension.getBlock(p)?.typeId; } catch { return undefined; }
}

/** The 10 frame blocks around an opening (origin = bottom-left opening cell). Corners excluded. */
export function frameCells(origin, axis) {
  const cells = [];
  for (let i = 0; i < WIDTH; i++) cells.push(at(origin, axis, i, -1), at(origin, axis, i, HEIGHT));
  for (let j = 0; j < HEIGHT; j++) cells.push(at(origin, axis, -1, j), at(origin, axis, WIDTH, j));
  return cells;
}
export function interiorCells(origin, axis) {
  const cells = [];
  for (let i = 0; i < WIDTH; i++) for (let j = 0; j < HEIGHT; j++) cells.push(at(origin, axis, i, j));
  return cells;
}

/** Find a complete 4x5 moss-brick frame whose 2x3 opening contains point p. */
export function findFrame(dimension, point) {
  const p = floorVec(point);
  for (const axis of ['x', 'z']) {
    for (let along = 0; along < WIDTH; along++) {
      for (let up = 0; up < HEIGHT; up++) {
        const origin = at(p, axis, -along, -up);
        if (!interiorCells(origin, axis).every(c => OPENINGS.includes(typeAt(dimension, c)))) continue;
        if (frameCells(origin, axis).every(c => typeAt(dimension, c) === B.frame)) return { origin, axis };
      }
    }
  }
  return undefined;
}

const FACE_OFFSETS = { Up: [0, 1, 0], Down: [0, -1, 0], North: [0, 0, -1], South: [0, 0, 1], East: [1, 0, 0], West: [-1, 0, 0] };
/** Opening cells to test for a flint-and-steel click: the clicked face first, then all neighbours. */
export function ignitionCandidates(block, face) {
  const l = block.location;
  const list = [];
  const push = d => list.push({ x: l.x + d[0], y: l.y + d[1], z: l.z + d[2] });
  if (FACE_OFFSETS[face]) push(FACE_OFFSETS[face]);
  if (block.typeId === B.frame) for (const d of Object.values(FACE_OFFSETS)) push(d);
  return list;
}

export function portalPermutation(axis) {
  return BlockPermutation.resolve(B.portal, { 'gc:axis': axis });
}
export function lightPortal(dimension, frame) {
  const permutation = portalPermutation(frame.axis);
  for (const c of interiorCells(frame.origin, frame.axis)) dimension.getBlock(c)?.setPermutation(permutation);
  const middle = at(frame.origin, frame.axis, 1, 1);
  try { dimension.playSound('fire.ignite', middle); } catch {}
  try { dimension.playSound('block.end_portal.spawn', middle, { volume: 0.4 }); } catch {}
}
export function tryIgnite(dimension, block, face) {
  for (const candidate of ignitionCandidates(block, face)) {
    const frame = findFrame(dimension, candidate);
    if (frame) { lightPortal(dimension, frame); return frame; }
  }
  return undefined;
}

/** When a frame or portal block disappears, extinguish all connected portal blocks. */
export function collapsePortal(dimension, location) {
  const start = floorVec(location);
  const seen = new Set([key(start)]);
  const queue = [start];
  const air = BlockPermutation.resolve('minecraft:air');
  let removed = 0;
  if (typeAt(dimension, start) === B.portal) { dimension.getBlock(start)?.setPermutation(air); removed++; }
  while (queue.length && seen.size < 96) {
    const p = queue.shift();
    for (const d of Object.values(FACE_OFFSETS)) {
      const n = { x: p.x + d[0], y: p.y + d[1], z: p.z + d[2] };
      if (seen.has(key(n))) continue;
      seen.add(key(n));
      if (typeAt(dimension, n) !== B.portal) continue;
      dimension.getBlock(n)?.setPermutation(air);
      removed++;
      queue.push(n);
    }
  }
  return removed;
}

// ------------------------------------------------------------------ noise
let SEED = 1337;
export function setSeed(value) {
  let h = 2166136261;
  for (const ch of String(value)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  SEED = h | 0;
}
export function hash(x, z, salt = 0) {
  let h = Math.imul(x | 0, 374761393) ^ Math.imul(z | 0, 668265263) ^ Math.imul(SEED ^ salt, 2246822519);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function smooth(t) { return t * t * (3 - 2 * t); }
function valueNoise(x, z, salt) {
  const x0 = Math.floor(x), z0 = Math.floor(z), tx = smooth(x - x0), tz = smooth(z - z0);
  const a = hash(x0, z0, salt), b = hash(x0 + 1, z0, salt), c = hash(x0, z0 + 1, salt), d = hash(x0 + 1, z0 + 1, salt);
  const top = a + (b - a) * tx, bottom = c + (d - c) * tx;
  return top + (bottom - top) * tz;
}
/** Surface height of the realm at an integer column. Deterministic across chunk seams. */
export function surfaceHeight(x, z) {
  const hills = valueNoise(x / 64, z / 64, 11) * 22;
  const bumps = valueNoise(x / 20, z / 20, 23) * 7;
  const detail = valueNoise(x / 7, z / 7, 37) * 2;
  return Math.round(50 + hills + bumps + detail);
}
/** Glowcap groves are luminous mushroom forests; the rest is mossbark forest. */
export function biome(x, z) { return valueNoise(x / 96, z / 96, 51) > 0.62 ? 'glowcap' : 'mossbark'; }

// ------------------------------------------------------------ world edits
const permCache = new Map();
function perm(id) {
  if (!permCache.has(id)) permCache.set(id, BlockPermutation.resolve(id));
  return permCache.get(id);
}
function put(dimension, p, id, onlyAir = false) {
  try {
    const block = dimension.getBlock(p);
    if (!block || (onlyAir && !block.isAir)) return false;
    block.setPermutation(perm(id));
    return true;
  } catch { return false; }
}
function fill(dimension, from, to, id) {
  if (to.y < from.y) return;
  try { dimension.fillBlocks(new BlockVolume(from, to), perm(id)); } catch (error) { warn('Fill', error); }
}
const SOFT = new Set(['minecraft:air', B.mossSapling, B.glowSprout, B.fern, B.mushroom]);

/** Trees; also grown by the two saplings in any dimension (only replaces air/plants). */
export function growTree(dimension, base, kind, rand = Math.random) {
  const b = floorVec(base);
  const clear = h => { for (let y = 0; y < h; y++) if (!SOFT.has(typeAt(dimension, { x: b.x, y: b.y + y, z: b.z }))) return false; return true; };
  if (kind === 'glowcap') {
    const h = 4 + Math.floor(rand() * 3);
    if (!clear(h + 2)) return false;
    for (let y = 0; y < h; y++) put(dimension, { x: b.x, y: b.y + y, z: b.z }, B.glowStem);
    for (let dx = -2; dx <= 2; dx++) for (let dz = -2; dz <= 2; dz++) {
      if (Math.abs(dx) === 2 && Math.abs(dz) === 2) continue;
      put(dimension, { x: b.x + dx, y: b.y + h, z: b.z + dz }, B.glowCap, true);
      if (Math.abs(dx) === 2 || Math.abs(dz) === 2) put(dimension, { x: b.x + dx, y: b.y + h - 1, z: b.z + dz }, B.glowCap, true);
    }
    for (let dx = -1; dx <= 1; dx++) for (let dz = -1; dz <= 1; dz++)
      put(dimension, { x: b.x + dx, y: b.y + h + 1, z: b.z + dz }, B.glowCap, true);
    return true;
  }
  const h = 5 + Math.floor(rand() * 3);
  if (!clear(h)) return false;
  for (let y = 0; y < h; y++) put(dimension, { x: b.x, y: b.y + y, z: b.z }, B.mossLog);
  for (let dy = -2; dy <= 1; dy++) {
    const r = dy >= 0 ? 1 : 2;
    for (let dx = -r; dx <= r; dx++) for (let dz = -r; dz <= r; dz++) {
      if (Math.abs(dx) === r && Math.abs(dz) === r && rand() < 0.6) continue;
      put(dimension, { x: b.x + dx, y: b.y + h + dy, z: b.z + dz }, B.mossLeaves, true);
    }
  }
  put(dimension, { x: b.x, y: b.y + h + 2, z: b.z }, B.mossLeaves, true);
  // Hanging moss beards under the canopy.
  for (const [dx, dz] of [[2, 0], [-2, 0], [0, 2], [0, -2]])
    if (rand() < 0.5) put(dimension, { x: b.x + dx, y: b.y + h - 3, z: b.z + dz }, B.mossLeaves, true);
  return true;
}

/** 5x5 mossbark hut with a moss-brick roof and a glowcap lamp; the door faces south. */
export function goblinHut(dimension, o) {
  for (let dx = 0; dx < 5; dx++) for (let dz = 0; dz < 5; dz++) {
    put(dimension, { x: o.x + dx, y: o.y, z: o.z + dz }, B.planks);
    for (let dy = 1; dy <= 3; dy++) {
      const wall = dx === 0 || dx === 4 || dz === 0 || dz === 4;
      const door = dz === 4 && dx === 2 && dy <= 2;
      const window = wall && dy === 2 && (dx === 2 || dz === 2) && dz !== 4;
      put(dimension, { x: o.x + dx, y: o.y + dy, z: o.z + dz }, wall && !door && !window ? B.planks : 'minecraft:air');
    }
    put(dimension, { x: o.x + dx, y: o.y + 4, z: o.z + dz }, B.frame);
  }
  put(dimension, { x: o.x + 2, y: o.y + 5, z: o.z + 2 }, B.frame);
  put(dimension, { x: o.x + 2, y: o.y + 3, z: o.z + 2 }, B.glowCap);
}

function floorOf(dimension) {
  return Math.max(FLOOR_Y, dimension.heightRange?.min ?? -64);
}
export function isGenerated(dimension, cx, cz) {
  return typeAt(dimension, { x: cx * 16, y: floorOf(dimension), z: cz * 16 }) === 'minecraft:bedrock';
}

/** Generate one 16x16 chunk. Generator for system.runJob: yields per column. */
export function* generateChunk(dimension, cx, cz, spawn = true) {
  const x0 = cx * 16, z0 = cz * 16;
  const floor = floorOf(dimension);
  const ceiling = (dimension.heightRange?.max ?? 320) - 24;
  // Column (0,0) carries the "generated" bedrock marker and is written LAST,
  // so a chunk interrupted by unloading/reload is simply generated again.
  const columns = [];
  for (let lx = 0; lx < 16; lx++) for (let lz = 0; lz < 16; lz++) if (lx || lz) columns.push([lx, lz]);
  columns.push([0, 0]);
  const tops = new Map();
  for (const [lx, lz] of columns) {
    const x = x0 + lx, z = z0 + lz;
    if (!dimension.isChunkLoaded({ x, y: floor, z })) return false;
    const h = Math.min(ceiling, Math.max(floor + 6, surfaceHeight(x, z)));
    tops.set(lx + ',' + lz, h);
    const glow = biome(x, z) === 'glowcap';
    fill(dimension, { x, y: floor + 1, z }, { x, y: h - 4, z }, B.stone);
    fill(dimension, { x, y: h - 3, z }, { x, y: h - 1, z }, B.soil);
    const underwater = h < SEA_Y;
    put(dimension, { x, y: h, z }, underwater ? B.soil : (glow && hash(x, z, 5) < 0.3 ? 'minecraft:moss_block' : B.grass));
    if (underwater) fill(dimension, { x, y: h + 1, z }, { x, y: SEA_Y, z }, 'minecraft:water');
    else {
      const r = hash(x, z, 7);
      if (r < 0.05) put(dimension, { x, y: h + 1, z }, B.fern);
      else if (r < (glow ? 0.1 : 0.065)) put(dimension, { x, y: h + 1, z }, B.mushroom);
    }
    const ore = hash(x, z, 13), depth = Math.max(1, h - floor - 8);
    if (ore < 0.018) put(dimension, { x, y: floor + 2 + Math.floor(hash(x, z, 17) * depth), z }, B.ore);
    else if (ore > 0.992) put(dimension, { x, y: floor + 2 + Math.floor(hash(x, z, 19) * depth), z }, B.crystal);
    put(dimension, { x, y: floor, z }, 'minecraft:bedrock');
    yield;
  }
  // Decorations stay inside this chunk and never touch ungenerated neighbours.
  let state = Math.floor(hash(cx, cz, 101) * 2147483646) + 1;
  const rand = () => (state = (state * 16807) % 2147483647) / 2147483647;
  const hut = hash(cx, cz, 103) < 0.07;
  if (hut) {
    const h = tops.get('5,5');
    if (h >= SEA_Y) {
      for (let dx = 0; dx < 5; dx++) for (let dz = 0; dz < 5; dz++) {
        const x = x0 + 5 + dx, z = z0 + 5 + dz, top = tops.get((5 + dx) + ',' + (5 + dz));
        fill(dimension, { x, y: top + 1, z }, { x, y: h, z }, B.planks);         // level the ground
        fill(dimension, { x, y: h + 1, z }, { x, y: Math.max(h + 6, top + 2), z }, 'minecraft:air');
      }
      goblinHut(dimension, { x: x0 + 5, y: h, z: z0 + 5 });
    }
  }
  const glowChunk = biome(x0 + 8, z0 + 8) === 'glowcap';
  const attempts = glowChunk ? 3 : 6;
  for (let i = 0; i < attempts; i++) {
    const lx = 2 + Math.floor(rand() * 12), lz = 2 + Math.floor(rand() * 12);
    if (hut && lx >= 3 && lx <= 11 && lz >= 3 && lz <= 11) continue;
    const h = tops.get(lx + ',' + lz);
    if (h < SEA_Y) continue;
    growTree(dimension, { x: x0 + lx, y: h + 1, z: z0 + lz }, glowChunk || rand() < 0.15 ? 'glowcap' : 'mossbark', rand);
    yield;
  }
  if (spawn) spawnGoblins(dimension, cx, cz, tops, rand);
  return true;
}

function spawnGoblins(dimension, cx, cz, tops, rand) {
  const roll = hash(cx, cz, 211);
  let type;
  if (roll < 0.025) type = 'gc:giant';          // gets its archer crew from main.js
  else if (roll < 0.16) type = 'gc:archer';
  if (!type) return;
  const count = type === 'gc:archer' ? 1 + Math.floor(rand() * 2) : 1;
  for (let i = 0; i < count; i++) {
    const lx = 3 + Math.floor(rand() * 10), lz = 3 + Math.floor(rand() * 10);
    const h = tops.get(lx + ',' + lz);
    if (h < SEA_Y) continue;
    try { dimension.spawnEntity(type, { x: cx * 16 + lx + 0.5, y: h + 1, z: cz * 16 + lz + 0.5 }); }
    catch (error) { warn('Goblin spawn', error); }
  }
}

// ---------------------------------------------------------- generation queue
const queue = [];
const queued = new Set();
let working = false;
export function runGenerator(generator) {
  return new Promise(resolve => {
    system.runJob((function* () {
      let result = false;
      try { result = yield* generator; } catch (error) { warn('Generation', error); }
      resolve(result);
    })());
  });
}
async function drain() {
  if (working) return;
  working = true;
  try {
    while (queue.length) {
      const { cx, cz } = queue.shift();
      try {
        const dimension = world.getDimension(REALM);
        if (!isGenerated(dimension, cx, cz)) await runGenerator(generateChunk(dimension, cx, cz));
      } finally { queued.delete(cx + ',' + cz); }
    }
  } finally { working = false; }
}
/** Queue loaded, ungenerated chunks around `center`, nearest first. */
export function requestChunks(dimension, center, radius = GENERATE_RADIUS) {
  const ccx = Math.floor(center.x / 16), ccz = Math.floor(center.z / 16), y = floorOf(dimension);
  const wanted = [];
  for (let dx = -radius; dx <= radius; dx++) for (let dz = -radius; dz <= radius; dz++) {
    const cx = ccx + dx, cz = ccz + dz;
    if (queued.has(cx + ',' + cz)) continue;
    if (!dimension.isChunkLoaded({ x: cx * 16, y, z: cz * 16 }) || isGenerated(dimension, cx, cz)) continue;
    wanted.push({ cx, cz, d: dx * dx + dz * dz });
  }
  wanted.sort((a, b) => a.d - b.d);
  for (const w of wanted) { queued.add(w.cx + ',' + w.cz); queue.push(w); }
  if (wanted.length) drain();
  return wanted.length;
}
async function generateAround(dimension, center, radius) {
  const ccx = Math.floor(center.x / 16), ccz = Math.floor(center.z / 16);
  for (let dx = -radius; dx <= radius; dx++) for (let dz = -radius; dz <= radius; dz++)
    if (!isGenerated(dimension, ccx + dx, ccz + dz)) await runGenerator(generateChunk(dimension, ccx + dx, ccz + dz));
}

// ------------------------------------------------------------------ travel
const LINK = 'gc:portal/';
export function portalId(dimensionId, origin, axis) { return LINK + dimensionId + '|' + key(origin) + '|' + axis; }
export function readLink(dimensionId, frame) {
  try {
    const raw = world.getDynamicProperty(portalId(dimensionId, frame.origin, frame.axis));
    return typeof raw === 'string' ? JSON.parse(raw) : undefined;
  } catch { return undefined; }
}
export function writeLink(a, b) {
  world.setDynamicProperty(portalId(a.dimension, a.origin, a.axis), JSON.stringify(b));
  world.setDynamicProperty(portalId(b.dimension, b.origin, b.axis), JSON.stringify(a));
}

/** Build a lit 4x5 frame standing on `ground` (its bottom row replaces ground+1) with a platform. */
export function buildPortal(dimension, ground, axis) {
  const origin = { x: ground.x, y: ground.y + 1, z: ground.z };
  for (let along = -2; along <= WIDTH + 1; along++) for (let across = -2; across <= 2; across++) {
    if (across === 0 && along >= -1 && along <= WIDTH) continue;
    for (let up = 0; up <= HEIGHT + 1; up++) put(dimension, at(origin, axis, along, up, across), 'minecraft:air');
    // Walkway in front of and behind the portal, so nobody lands in a lake or a hole.
    put(dimension, at(origin, axis, along, -1, across), B.frame);
  }
  for (let along = -1; along <= WIDTH; along++) for (let up = -1; up <= HEIGHT; up++) {
    const edge = along === -1 || along === WIDTH || up === -1 || up === HEIGHT;
    put(dimension, at(origin, axis, along, up), edge ? B.frame : 'minecraft:air');
  }
  const frame = { origin, axis };
  lightPortal(dimension, frame);
  return frame;
}

export function intact(dimension, frame) {
  return interiorCells(frame.origin, frame.axis).every(c => typeAt(dimension, c) === B.portal);
}

let areaSerial = 0;
async function withArea(dimension, center, radius, work) {
  const id = 'gc_realm_' + system.currentTick + '_' + (++areaSerial);
  const range = dimension.heightRange ?? { min: -64, max: 320 };
  await world.tickingAreaManager.createTickingArea(id, {
    dimension,
    from: { x: center.x - radius, y: range.min, z: center.z - radius },
    to: { x: center.x + radius, y: range.max - 1, z: center.z + radius },
  });
  try { return await work(); }
  finally { system.runTimeout(() => { try { world.tickingAreaManager.removeTickingArea(id); } catch {} }, 100); }
}

/** Ground height at a column of a vanilla dimension (portal returns). */
function groundY(dimension, x, z) {
  const range = dimension.heightRange ?? { min: -64, max: 320 };
  if (dimension.id === 'minecraft:nether') {
    for (let y = 32; y < 120; y++) {
      const t = typeAt(dimension, { x, y, z }), up = typeAt(dimension, { x, y: y + 1, z });
      if (t && t !== 'minecraft:air' && t !== 'minecraft:lava' && up === 'minecraft:air') return y;
    }
    return 64;
  }
  const top = dimension.getTopmostBlock({ x, z });
  return Math.max(range.min + 2, Math.min(range.max - 8, top?.location.y ?? 64));
}

const traveling = new Set();
const cooldown = new Map();
const inPortal = new Map();

export async function travel(player, frame) {
  if (traveling.has(player.id)) return false;
  traveling.add(player.id);
  try {
    const fromId = player.dimension.id;
    const toRealm = fromId !== REALM;
    const here = { dimension: fromId, origin: frame.origin, axis: frame.axis };
    let link = readLink(fromId, frame);
    const destId = link?.dimension ?? (toRealm ? REALM : 'minecraft:overworld');
    const dest = world.getDimension(destId);
    const center = link?.origin ?? { x: frame.origin.x, y: frame.origin.y, z: frame.origin.z };
    const target = await withArea(dest, center, 32, async () => {
      if (destId === REALM) await generateAround(dest, center, 1);
      if (link && intact(dest, link)) return link;
      const y = destId === REALM ? surfaceHeight(center.x, center.z) : groundY(dest, center.x, center.z);
      const built = buildPortal(dest, { x: center.x, y: Math.max(y, destId === REALM ? SEA_Y : y), z: center.z }, frame.axis);
      link = { dimension: destId, origin: built.origin, axis: built.axis };
      writeLink(here, link);
      return link;
    });
    // Arrive standing in FRONT of the portal, looking away from it.
    const spot = at(target.origin, target.axis, 1, 0, 1);
    const ahead = at(target.origin, target.axis, 1, 1, 6);
    cooldown.set(player.id, system.currentTick + COOLDOWN);
    player.teleport({ x: spot.x + 0.5, y: spot.y, z: spot.z + 0.5 }, { dimension: dest, facingLocation: { x: ahead.x + 0.5, y: ahead.y, z: ahead.z + 0.5 } });
    try { dest.playSound('mob.endermen.portal', spot); } catch {}
    try {
      player.onScreenDisplay.setTitle(toRealm ? '§2Regno dei Goblin' : '§aSei tornato', {
        subtitle: toRealm ? '§7Muschio, funghi luminosi... e goblin!' : '§7Il portale resta collegato',
        fadeInDuration: 10, stayDuration: 50, fadeOutDuration: 20,
      });
    } catch {}
    if (toRealm) system.runTimeout(() => { try { requestChunks(dest, player.location); } catch {} }, 20);
    return true;
  } catch (error) {
    warn('Travel', error);
    try { player.sendMessage('§cIl portale goblin non riesce a caricare la destinazione. Riprova tra poco.'); } catch {}
    return false;
  } finally { traveling.delete(player.id); }
}

export function portalUnder(player) {
  const l = player.location;
  for (const dy of [0, 1]) {
    const p = { x: Math.floor(l.x), y: Math.floor(l.y) + dy, z: Math.floor(l.z) };
    if (typeAt(player.dimension, p) === B.portal) return p;
  }
  return undefined;
}

/** Every 5 ticks: players standing in a portal for 3 s (Creative: instantly) travel. */
export function tickPlayers(players = world.getAllPlayers(), step = 5) {
  for (const player of players) {
    try {
      if (!player.isValid || traveling.has(player.id)) continue;
      const cell = portalUnder(player);
      if (!cell) { inPortal.delete(player.id); continue; }
      if ((cooldown.get(player.id) ?? 0) > system.currentTick) continue;
      const time = (inPortal.get(player.id) ?? 0) + step;
      inPortal.set(player.id, time);
      if (time === step) try { player.addEffect('nausea', 80, { amplifier: 0, showParticles: false }); } catch {}
      const mode = player.getGameMode();
      const needed = mode === GameMode.Creative || mode === GameMode.Spectator ? WAIT_CREATIVE : WAIT_SURVIVAL;
      if (time < needed) continue;
      inPortal.delete(player.id);
      const frame = findFrame(player.dimension, cell);
      if (frame) travel(player, frame);
      else collapsePortal(player.dimension, cell);   // broken frame: the portal goes out
    } catch (error) { warn('Portal check', error); }
  }
}

// ---------------------------------------------------------------- saplings
export const SAPLINGS = { [B.mossSapling]: 'mossbark', [B.glowSprout]: 'glowcap' };
export function growSapling(block, rand = Math.random) {
  const kind = SAPLINGS[block.typeId];
  if (!kind) return false;
  const dimension = block.dimension, base = block.location, id = block.typeId;
  block.setPermutation(perm('minecraft:air'));
  if (growTree(dimension, base, kind, rand)) return true;
  dimension.getBlock(base)?.setPermutation(perm(id));
  return false;
}

// ------------------------------------------------------------------ wiring
system.beforeEvents.startup.subscribe(event => {
  try { event.dimensionRegistry.registerCustomDimension(REALM); }
  catch (error) { console.warn('[Goblin Realm] Dimension registration: ' + error); }
  event.blockComponentRegistry.registerCustomComponent('gc:sapling', {
    onRandomTick({ block }) { if (Math.random() < 0.2) try { growSapling(block); } catch {} },
    onPlayerInteract({ block, player }) {
      const equip = player?.getComponent('minecraft:equippable');
      const hand = equip?.getEquipment('Mainhand');
      if (hand?.typeId !== 'minecraft:bone_meal') return;
      if (player.getGameMode() !== GameMode.Creative) {
        if (hand.amount > 1) { hand.amount -= 1; equip.setEquipment('Mainhand', hand); }
        else equip.setEquipment('Mainhand', undefined);
      }
      const l = block.location;
      try { block.dimension.spawnParticle('minecraft:crop_growth_emitter', { x: l.x + 0.5, y: l.y + 0.5, z: l.z + 0.5 }); } catch {}
      if (Math.random() < 0.45) growSapling(block);
    },
  });
  event.blockComponentRegistry.registerCustomComponent('gc:portal_fx', {
    onTick({ block, dimension }) {
      const l = block.location;
      try { dimension.spawnParticle('gc:goblin_portal_spark', { x: l.x + Math.random(), y: l.y + Math.random(), z: l.z + Math.random() }); } catch {}
    },
  });
});

world.afterEvents.worldLoad.subscribe(() => { setSeed(world.seed); });

// Flint and steel / fire charge on a frame. Both signals are handled because
// item-use-on and block-interaction reporting differ between platforms; the
// per-tick key prevents a double ignition.
let lastIgnite = '';
function onIgnite(player, block, face, item) {
  if (!IGNITERS.includes(item?.typeId)) return;
  const snapshot = { typeId: block.typeId, location: block.location };
  const dimension = block.dimension;
  const id = system.currentTick + '|' + key(snapshot.location);
  if (id === lastIgnite) return;
  lastIgnite = id;
  system.run(() => {
    try {
      if (tryIgnite(dimension, snapshot, face)) player?.onScreenDisplay.setActionBar('§2Il portale goblin si accende!');
    } catch (error) { warn('Ignite', error); }
  });
}
world.afterEvents.playerInteractWithBlock.subscribe(e => {
  if (e.isFirstEvent) onIgnite(e.player, e.block, e.blockFace, e.beforeItemStack ?? e.itemStack);
});
world.afterEvents.itemStartUseOn.subscribe(e => onIgnite(e.source, e.block, e.blockFace, e.itemStack));

function onBlockGone(dimension, location, typeId) {
  if (typeId !== B.frame && typeId !== B.portal) return;
  system.run(() => { try { collapsePortal(dimension, location); } catch (error) { warn('Collapse', error); } });
}
world.afterEvents.playerBreakBlock.subscribe(e => onBlockGone(e.block.dimension, e.block.location, e.brokenBlockPermutation.type.id));
world.afterEvents.blockExplode.subscribe(e => onBlockGone(e.dimension, e.block.location, e.explodedBlockPermutation.type.id));

system.runInterval(() => tickPlayers(), 5);
system.runInterval(() => {
  let dimension;
  try { dimension = world.getDimension(REALM); } catch { return; }
  for (const player of world.getAllPlayers()) {
    try { if (player.dimension.id === REALM) requestChunks(dimension, player.location); }
    catch (error) { warn('Chunk request', error); }
  }
}, 20);
