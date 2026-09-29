// Run: node --experimental-vm-modules --test tests/goblin_realm.test.mjs
// Simulated @minecraft/server: voxel world, events, jobs. Not a Minecraft runtime.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm';

const source = readFileSync(new URL('../minecraft/goblin_realm.js', import.meta.url), 'utf8');
const GameMode = { Creative: 'Creative', Spectator: 'Spectator', Survival: 'Survival', Adventure: 'Adventure' };
const k = p => `${p.x},${p.y},${p.z}`;

function makeDimension(id, heightRange = { min: -64, max: 320 }) {
  const blocks = new Map(), entities = [], sounds = [];
  const dim = {
    id, heightRange, blocks, entities, sounds,
    getBlock(p) {
      const loc = { x: Math.floor(p.x), y: Math.floor(p.y), z: Math.floor(p.z) };
      if (loc.y < heightRange.min || loc.y >= heightRange.max) return undefined;
      const entry = () => blocks.get(k(loc));
      return {
        location: loc, dimension: dim,
        get typeId() { return entry()?.id ?? 'minecraft:air'; },
        get isAir() { return (entry()?.id ?? 'minecraft:air') === 'minecraft:air'; },
        get permutation() { return entry(); },
        setPermutation(perm) { if (perm.id === 'minecraft:air') blocks.delete(k(loc)); else blocks.set(k(loc), perm); },
      };
    },
    fillBlocks(volume, perm) {
      const { from, to } = volume;
      for (let x = Math.min(from.x, to.x); x <= Math.max(from.x, to.x); x++)
        for (let y = Math.min(from.y, to.y); y <= Math.max(from.y, to.y); y++)
          for (let z = Math.min(from.z, to.z); z <= Math.max(from.z, to.z); z++) dim.getBlock({ x, y, z }).setPermutation(perm);
    },
    isChunkLoaded: () => true,
    getTopmostBlock({ x, z }) {
      for (let y = heightRange.max - 1; y >= heightRange.min; y--) if (blocks.has(k({ x, y, z }))) return dim.getBlock({ x, y, z });
    },
    spawnEntity(type, location) { const e = { typeId: type, location }; entities.push(e); return e; },
    spawnParticle() {}, playSound(name) { sounds.push(name); },
  };
  return dim;
}

async function load() {
  const dims = {
    'minecraft:overworld': makeDimension('minecraft:overworld'),
    'minecraft:nether': makeDimension('minecraft:nether', { min: 0, max: 128 }),
    'gc:goblin_realm': makeDimension('gc:goblin_realm', { min: 0, max: 256 }),
  };
  const subs = {}, props = new Map(), areas = [], registered = [], components = {}, warnings = [];
  const signal = name => ({ subscribe(fn) { subs[name] = fn; return fn; } });
  const system = {
    currentTick: 0,
    beforeEvents: { startup: signal('startup') },
    runInterval(fn, n) { (subs['interval' + n] = fn); },
    run(fn) { fn(); }, runTimeout(fn) { fn(); },
    runJob(gen) { while (!gen.next().done); },
  };
  const world = {
    seed: '12345',
    getDimension(id) { const d = dims[id.includes(':') ? id : 'minecraft:' + id]; if (!d) throw new Error('no dim ' + id); return d; },
    getAllPlayers: () => [],
    getDynamicProperty: key => props.get(key), setDynamicProperty: (key, v) => props.set(key, v),
    tickingAreaManager: {
      async createTickingArea(id, options) { areas.push({ id, options }); },
      removeTickingArea(id) { const i = areas.findIndex(a => a.id === id); if (i >= 0) areas.splice(i, 1); },
    },
    afterEvents: Object.fromEntries(['worldLoad', 'playerInteractWithBlock', 'itemStartUseOn', 'playerBreakBlock', 'blockExplode'].map(n => [n, signal(n)])),
  };
  class BlockVolume { constructor(from, to) { this.from = from; this.to = to; } }
  const BlockPermutation = { resolve: (id, states = {}) => ({ id, states, type: { id } }) };
  const context = createContext({ console: { warn: x => warnings.push(x) }, Math, JSON, Promise, Map, Set, Object, String, Number, Array, Error });
  const mock = new SyntheticModule(['world', 'system', 'BlockPermutation', 'BlockVolume', 'GameMode'], function () {
    this.setExport('world', world); this.setExport('system', system); this.setExport('BlockPermutation', BlockPermutation);
    this.setExport('BlockVolume', BlockVolume); this.setExport('GameMode', GameMode);
  }, { context });
  const module = new SourceTextModule(source, { context });
  await module.link(() => mock); await module.evaluate();
  subs.startup({
    dimensionRegistry: { registerCustomDimension: id => registered.push(id) },
    blockComponentRegistry: { registerCustomComponent: (name, c) => { components[name] = c; } },
  });
  subs.worldLoad?.({});
  return { api: module.namespace, dims, subs, props, areas, registered, components, warnings, system, world };
}

const FRAME = 'gc:goblin_moss_bricks', PORTAL = 'gc:goblin_portal';
function buildFrame(dim, origin, axis, { corners = false, skip } = {}) {
  const at = (a, u) => axis === 'x' ? { x: origin.x + a, y: origin.y + u, z: origin.z } : { x: origin.x, y: origin.y + u, z: origin.z + a };
  for (let a = -1; a <= 2; a++) for (let u = -1; u <= 3; u++) {
    const edge = a === -1 || a === 2 || u === -1 || u === 3;
    const corner = (a === -1 || a === 2) && (u === -1 || u === 3);
    if (!edge || (corner && !corners)) continue;
    const p = at(a, u);
    if (skip && k(skip) === k(p)) continue;
    dim.getBlock(p).setPermutation({ id: FRAME });
  }
  return at;
}
const player = (dim, location, mode = GameMode.Survival) => ({
  id: 'p' + Math.random(), isValid: true, dimension: dim, location, mode, effects: [], titles: [], messages: [], teleports: [],
  getGameMode() { return this.mode; }, addEffect(e) { this.effects.push(e); },
  onScreenDisplay: { setTitle(t) { player.last = t; }, setActionBar() {} },
  sendMessage(m) { this.messages.push(m); },
  teleport(location, options) { this.teleports.push({ location, options }); this.location = location; this.dimension = options.dimension; },
});

test('registers the custom dimension and block components at startup', async () => {
  const { registered, components } = await load();
  assert.deepEqual(registered, ['gc:goblin_realm']);
  assert.ok(components['gc:sapling'].onRandomTick && components['gc:sapling'].onPlayerInteract);
  assert.ok(components['gc:portal_fx'].onTick);
});

test('frame is exactly 4 wide x 5 tall with a 2x3 opening, on both axes', async () => {
  const { api, dims } = await load();
  const dim = dims['minecraft:overworld'];
  assert.equal(api.frameCells({ x: 0, y: 0, z: 0 }, 'x').length, 10);
  assert.equal(api.interiorCells({ x: 0, y: 0, z: 0 }, 'x').length, 6);
  for (const [axis, origin] of [['x', { x: 10, y: 65, z: 3 }], ['z', { x: -40, y: 70, z: 8 }]]) {
    const at = buildFrame(dim, origin, axis);
    for (let a = 0; a < 2; a++) for (let u = 0; u < 3; u++) {
      const found = api.findFrame(dim, at(a, u));
      assert.deepEqual(JSON.parse(JSON.stringify(found)), { origin, axis }, `${axis} ${a},${u}`);
    }
  }
});

test('corners are optional and incomplete frames, blocked openings or wrong sizes do not light', async () => {
  const { api, dims } = await load();
  const dim = dims['minecraft:overworld'];
  buildFrame(dim, { x: 0, y: 64, z: 0 }, 'x', { corners: true });
  assert.ok(api.findFrame(dim, { x: 0, y: 64, z: 0 }));
  const d2 = dims['minecraft:nether'];
  buildFrame(d2, { x: 0, y: 40, z: 0 }, 'x', { skip: { x: 2, y: 41, z: 0 } });
  assert.equal(api.findFrame(d2, { x: 0, y: 40, z: 0 }), undefined, 'missing brick');
  const d3 = dims['gc:goblin_realm'];
  buildFrame(d3, { x: 0, y: 70, z: 0 }, 'z');
  d3.getBlock({ x: 0, y: 71, z: 1 }).setPermutation({ id: 'minecraft:dirt' });
  assert.equal(api.findFrame(d3, { x: 0, y: 70, z: 0 }), undefined, 'blocked opening');
  // Vanilla obsidian does not count.
  const d4 = (await load()).dims['minecraft:overworld'];
  buildFrame(d4, { x: 0, y: 64, z: 0 }, 'x');
  for (const [p, b] of d4.blocks) d4.blocks.set(p, { id: 'minecraft:obsidian' });
  assert.equal((await load()).api.findFrame(d4, { x: 0, y: 64, z: 0 }), undefined);
});

test('flint and steel on the frame or inside the opening lights a 2x3 portal oriented to the frame', async () => {
  for (const [axis, clickOn, face] of [['x', { x: 0, y: 63, z: 0 }, 'Up'], ['z', { x: 0, y: 65, z: -1 }, 'South'], ['x', { x: -1, y: 65, z: 0 }, 'North']]) {
    const { dims, subs } = await load();
    const dim = dims['minecraft:overworld'];
    buildFrame(dim, { x: 0, y: 64, z: 0 }, axis);
    const block = dim.getBlock(clickOn);
    subs.playerInteractWithBlock({ isFirstEvent: true, beforeItemStack: { typeId: 'minecraft:flint_and_steel' }, block, blockFace: face,
      player: { onScreenDisplay: { setActionBar() {} } } });
    const portals = [...dim.blocks.values()].filter(b => b.id === PORTAL);
    assert.equal(portals.length, 6, axis + ' ' + face);
    assert.ok(portals.every(b => b.states['gc:axis'] === axis));
    assert.ok(dim.sounds.includes('fire.ignite'));
  }
});

test('other items do not light; fire charge does', async () => {
  const { dims, subs } = await load();
  const dim = dims['minecraft:overworld'];
  buildFrame(dim, { x: 0, y: 64, z: 0 }, 'x');
  const click = typeId => subs.itemStartUseOn({ source: { onScreenDisplay: { setActionBar() {} } }, itemStack: { typeId }, block: dim.getBlock({ x: 0, y: 63, z: 0 }), blockFace: 'Up' });
  click('minecraft:stick');
  assert.equal([...dim.blocks.values()].filter(b => b.id === PORTAL).length, 0);
  click('minecraft:fire_charge');
  assert.equal([...dim.blocks.values()].filter(b => b.id === PORTAL).length, 6);
});

test('breaking a frame brick extinguishes the whole portal', async () => {
  const { api, dims, subs } = await load();
  const dim = dims['minecraft:overworld'];
  buildFrame(dim, { x: 0, y: 64, z: 0 }, 'x');
  api.tryIgnite(dim, dim.getBlock({ x: 0, y: 63, z: 0 }), 'Up');
  dim.getBlock({ x: -1, y: 65, z: 0 }).setPermutation({ id: 'minecraft:air' });
  subs.playerBreakBlock({ block: dim.getBlock({ x: -1, y: 65, z: 0 }), brokenBlockPermutation: { type: { id: FRAME } } });
  assert.equal([...dim.blocks.values()].filter(b => b.id === PORTAL).length, 0);
});

test('terrain generation is deterministic, seamless and full of new blocks and trees', async () => {
  const { api, dims } = await load();
  const realm = dims['gc:goblin_realm'];
  for (let cx = 0; cx < 4; cx++) for (let cz = 0; cz < 4; cz++) {
    const gen = api.generateChunk(realm, cx, cz, false);
    let r; do r = gen.next(); while (!r.done);
    assert.equal(r.value, true);
    assert.ok(api.isGenerated(realm, cx, cz));
  }
  const counts = {};
  for (const b of realm.blocks.values()) counts[b.id] = (counts[b.id] ?? 0) + 1;
  for (const id of ['gc:goblin_stone', 'gc:goblin_soil', 'gc:goblin_grass', 'gc:mossbark_log', 'gc:mossbark_leaves', 'minecraft:bedrock'])
    assert.ok(counts[id] > 0, 'missing ' + id + ' ' + JSON.stringify(counts));
  assert.ok((counts['gc:goblin_fern'] ?? 0) + (counts['gc:goblin_mushroom'] ?? 0) > 10);
  assert.equal(api.surfaceHeight(15, 3) - api.surfaceHeight(16, 3) <= 3, true, 'no cliffs at chunk seams');
  for (let x = 0; x < 64; x++) assert.ok(Math.abs(api.surfaceHeight(x, 7) - api.surfaceHeight(x + 1, 7)) <= 3);
  assert.equal(api.surfaceHeight(123, -456), api.surfaceHeight(123, -456));
  // Both biomes exist over a large area.
  const kinds = new Set();
  for (let x = -2000; x < 2000; x += 37) for (let z = -2000; z < 2000; z += 41) kinds.add(api.biome(x, z));
  assert.deepEqual([...kinds].sort(), ['glowcap', 'mossbark']);
});

test('glowcap trees and huts appear somewhere, goblins spawn on land', async () => {
  const { api, dims } = await load();
  const realm = dims['gc:goblin_realm'];
  let glowChunk, hutChunk;
  for (let cx = -80; cx < 80 && !(glowChunk && hutChunk); cx++) for (let cz = -80; cz < 80; cz++) {
    if (!glowChunk && api.biome(cx * 16 + 8, cz * 16 + 8) === 'glowcap') glowChunk = [cx, cz];
    if (!hutChunk && api.hash(cx, cz, 103) < 0.07 && api.surfaceHeight(cx * 16 + 5, cz * 16 + 5) >= api.SEA_Y) hutChunk = [cx, cz];
  }
  for (const [cx, cz] of [glowChunk, hutChunk]) { const g = api.generateChunk(realm, cx, cz, true); while (!g.next().done); }
  const ids = new Set([...realm.blocks.values()].map(b => b.id));
  assert.ok(ids.has('gc:glowcap_stem') && ids.has('gc:glowcap_cap'), 'glowcap grove');
  assert.ok(ids.has('gc:mossbark_planks'), 'goblin hut');
  let spawned = 0;
  for (let c = 0; c < 200 && !spawned; c++) {
    if (api.hash(c, 0, 211) >= 0.16) continue;
    const g = api.generateChunk(realm, c, 0, true); while (!g.next().done);
    spawned = realm.entities.length;
  }
  assert.ok(spawned > 0 && realm.entities.every(e => ['gc:archer', 'gc:giant'].includes(e.typeId)));
});

test('an unloaded chunk stops generation without the "generated" marker', async () => {
  const { api, dims } = await load();
  const realm = dims['gc:goblin_realm'];
  let calls = 0;
  realm.isChunkLoaded = () => ++calls < 50;
  const g = api.generateChunk(realm, 0, 0, false);
  let r; do r = g.next(); while (!r.done);
  assert.equal(r.value, false);
  assert.equal(api.isGenerated(realm, 0, 0), false);
});

test('standing in a lit portal travels to the realm and back through linked portals', async () => {
  const { api, dims, props, areas } = await load();
  const ow = dims['minecraft:overworld'];
  for (let x = -6; x <= 6; x++) for (let z = -6; z <= 6; z++) ow.getBlock({ x, y: 63, z }).setPermutation({ id: 'minecraft:grass_block' });
  buildFrame(ow, { x: 0, y: 64, z: 0 }, 'x');
  api.tryIgnite(ow, ow.getBlock({ x: 0, y: 63, z: 0 }), 'Up');
  const p = player(ow, { x: 0.5, y: 64, z: 0.5 });
  for (let t = 0; t < 11; t++) api.tickPlayers([p]);
  assert.equal(p.teleports.length, 0, 'survival waits 3 seconds');
  api.tickPlayers([p]);
  await new Promise(r => setTimeout(r, 0));
  assert.equal(p.teleports.length, 1);
  assert.equal(p.dimension.id, 'gc:goblin_realm');
  assert.equal(areas.length, 0, 'ticking areas are released');
  const realm = dims['gc:goblin_realm'];
  const exit = api.findFrame(realm, { x: Math.floor(p.location.x), y: p.location.y, z: Math.floor(p.location.z) - 1 }) ??
    [...realm.blocks.entries()].find(([, b]) => b.id === PORTAL);
  assert.ok(exit, 'return portal built');
  assert.equal([...realm.blocks.values()].filter(b => b.id === PORTAL).length, 6, 'return portal is lit');
  const feet = realm.getBlock({ x: Math.floor(p.location.x), y: p.location.y - 1, z: Math.floor(p.location.z) });
  assert.notEqual(feet.typeId, 'minecraft:air', 'arrive on solid ground');
  assert.equal(realm.getBlock(p.location).typeId, 'minecraft:air', 'arrive in open air');
  assert.equal(props.size, 2, 'portals linked both ways');
  // Walk back into the return portal (creative: instant).
  const back = [...realm.blocks.entries()].find(([, b]) => b.id === PORTAL)[0].split(',').map(Number);
  api.system?.currentTick;
  p.mode = GameMode.Creative;
  p.location = { x: back[0] + 0.5, y: back[1], z: back[2] + 0.5 };
  p.teleports.length = 0;
  api.tickPlayers([p]);
  // Cooldown after arrival prevents instant ping-pong.
  assert.equal(p.teleports.length, 0);
});

test('return trip uses the stored link and lands next to the original portal', async () => {
  const env = await load();
  const { api, dims, system } = env;
  const ow = dims['minecraft:overworld'];
  for (let x = -6; x <= 6; x++) for (let z = -6; z <= 6; z++) ow.getBlock({ x, y: 63, z }).setPermutation({ id: 'minecraft:stone' });
  buildFrame(ow, { x: 0, y: 64, z: 0 }, 'z');
  api.tryIgnite(ow, ow.getBlock({ x: 0, y: 63, z: 0 }), 'Up');
  const p = player(ow, { x: 0.5, y: 64, z: 0.5 }, GameMode.Creative);
  await api.travel(p, api.findFrame(ow, { x: 0, y: 64, z: 0 }));
  assert.equal(p.dimension.id, 'gc:goblin_realm');
  const realm = dims['gc:goblin_realm'];
  const cell = [...realm.blocks.entries()].find(([, b]) => b.id === PORTAL)[0].split(',').map(Number);
  await api.travel(p, api.findFrame(realm, { x: cell[0], y: cell[1], z: cell[2] }));
  assert.equal(p.dimension.id, 'minecraft:overworld');
  assert.ok(Math.hypot(p.location.x - 0.5, p.location.z - 0.5) < 3, JSON.stringify(p.location));
  assert.equal([...ow.blocks.values()].filter(b => b.id === PORTAL).length, 6, 'original portal reused, not duplicated');
});

test('saplings grow new trees with bone meal and consume it in survival', async () => {
  const { dims, components } = await load();
  const ow = dims['minecraft:overworld'];
  ow.getBlock({ x: 0, y: 63, z: 0 }).setPermutation({ id: 'gc:goblin_grass' });
  ow.getBlock({ x: 0, y: 64, z: 0 }).setPermutation({ id: 'gc:mossbark_sapling' });
  const hand = { typeId: 'minecraft:bone_meal', amount: 5 };
  const equip = { getEquipment: () => hand, setEquipment: (_s, v) => { equip.last = v; } };
  const p = { getComponent: () => equip, getGameMode: () => GameMode.Survival };
  const random = Math.random; Math.random = () => 0.1;
  try { components['gc:sapling'].onPlayerInteract({ block: ow.getBlock({ x: 0, y: 64, z: 0 }), player: p }); }
  finally { Math.random = random; }
  assert.equal(equip.last.amount, 4);
  assert.equal(ow.getBlock({ x: 0, y: 64, z: 0 }).typeId, 'gc:mossbark_log');
  assert.ok([...ow.blocks.values()].some(b => b.id === 'gc:mossbark_leaves'));
});

test('every grown tree has its own trunk and its own crown (both kinds)', async () => {
  for (const [sapling, trunk, crown] of [['gc:mossbark_sapling', 'gc:mossbark_log', 'gc:mossbark_leaves'],
                                          ['gc:glowcap_sprout', 'gc:glowcap_stem', 'gc:glowcap_cap']]) {
    const { dims, api: R } = await load();
    const ow = dims['minecraft:overworld'];
    ow.getBlock({ x: 0, y: 63, z: 0 }).setPermutation({ id: 'gc:goblin_grass' });
    ow.getBlock({ x: 0, y: 64, z: 0 }).setPermutation({ id: sapling });
    assert.ok(R.growSapling(ow.getBlock({ x: 0, y: 64, z: 0 }), () => 0.5));
    let height = 0;
    while (ow.getBlock({ x: 0, y: 64 + height, z: 0 }).typeId === trunk) height++;
    assert.ok(height >= 4, sapling + ' trunk height ' + height);
    const leaves = [...ow.blocks.values()].filter(b => b.id === crown).length;
    assert.ok(leaves >= 20, sapling + ' crown blocks ' + leaves);
    assert.equal(ow.getBlock({ x: 0, y: 64 + height, z: 0 }).typeId, crown, 'crown sits on top of the trunk');
  }
});

test('a sapling without room stays a sapling instead of vanishing', async () => {
  const { dims, api: R } = await load();
  const ow = dims['minecraft:overworld'];
  ow.getBlock({ x: 0, y: 63, z: 0 }).setPermutation({ id: 'gc:goblin_grass' });
  ow.getBlock({ x: 0, y: 64, z: 0 }).setPermutation({ id: 'gc:mossbark_sapling' });
  ow.getBlock({ x: 0, y: 66, z: 0 }).setPermutation({ id: 'minecraft:stone' });
  assert.equal(R.growSapling(ow.getBlock({ x: 0, y: 64, z: 0 }), () => 0.5), false);
  assert.equal(ow.getBlock({ x: 0, y: 64, z: 0 }).typeId, 'gc:mossbark_sapling');
});
