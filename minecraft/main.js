import { world, system } from '@minecraft/server';
import { REALM } from './goblin_realm.js';

const SIDES = ['left', 'right'];
const DIMENSIONS = ['overworld', 'nether', 'the_end', REALM];
let lastWarning = -200;
function warn(context, error) {
  if (system.currentTick - lastWarning < 200) return;
  lastWarning = system.currentTick;
  console.warn('[Goblin Caravan] ' + context + ': ' + error);
}
function setChanged(entity, name, value) {
  if (entity.getProperty(name) !== value) entity.setProperty(name, value);
}
function setPacked(rider, packed) {
  if (rider.getProperty('gc:packed') !== packed) {
    rider.triggerEvent(packed ? 'gc:pack' : 'gc:unpack');
  }
}
function wrapAngle(angle) { return ((angle + 180) % 360 + 360) % 360 - 180; }
function clamp(value, max) { return Math.max(-max, Math.min(max, value)); }

// Populate only NEW giants. The persistent marker prevents duplicate crews on reload.
// Failed mounts are removed and retried, without re-creating successful riders.
world.afterEvents.entitySpawn.subscribe(({ entity }) => {
  if (entity.typeId !== 'gc:giant') return;
  system.runTimeout(() => {
    try {
      if (!entity.isValid || entity.getDynamicProperty('gc:crew_created')) return;
      entity.setDynamicProperty('gc:crew_created', true);
      const completed = new Set();
      const populate = (attempt) => {
        if (!entity.isValid) return;
        const rideable = entity.getComponent('minecraft:rideable');
        if (!rideable) return;
        // Respect archers already mounted by commands or another add-on.
        for (const rider of rideable.getRiders()) {
          if (rider.typeId !== 'gc:archer') continue;
          let slot = rider.getDynamicProperty('gc:crew_slot');
          if (slot !== 0 && slot !== 1) {
            slot = [0, 1].find(i => !completed.has(i));
            if (slot === undefined) continue;
            rider.setDynamicProperty('gc:crew_slot', slot);
          }
          completed.add(slot);
        }
        for (let slot = 0; slot < 2; slot++) {
          if (completed.has(slot)) continue;
          let rider;
          let mounted = false;
          try {
            const p = entity.location;
            rider = entity.dimension.spawnEntity('gc:archer', { x: p.x, y: p.y + 3.1, z: p.z });
            rider.setDynamicProperty('gc:crew_slot', slot);
            mounted = rideable.addRider(rider);
            if (mounted) completed.add(slot);
          } catch (error) {
            warn('Crew spawn', error);
          } finally {
            // Never leave an unmounted duplicate behind after a failed attempt.
            if (!mounted && rider?.isValid) rider.remove();
          }
        }
        if (completed.size < 2) {
          if (attempt < 4) system.runTimeout(() => {
            try { populate(attempt + 1); } catch (error) { warn('Crew retry', error); }
          }, 10);
          else warn('Crew spawn', 'Not enough space for both riders; no automatic respawn.');
        }
      };
      populate(0);
    } catch (error) { warn('Crew setup', error); }
  }, 2);
});

// Real entities retain vanilla targeting, arrows, 24 HP and death/dismount behavior.
// Only their meshes are hidden: the giant renders articulated copies attached to
// the backpack bone. No per-tick teleportation, duplicate damage or scripted arrows.
// Also runs in the Goblin Realm (gc:goblin_realm), where giants spawn naturally.
// Rebuild membership from loaded entities, not an in-memory spawn list: survives reload.
system.runInterval(() => {
  for (const dimensionId of DIMENSIONS) {
    try {
      let dimension;
      try { dimension = world.getDimension(dimensionId); } catch { continue; }
      const represented = new Set();
      for (const giant of dimension.getEntities({ type: 'gc:giant' })) {
        try {
          const riders = giant.getComponent('minecraft:rideable')?.getRiders() ?? [];
          const slots = [undefined, undefined];
          const pending = [];
          for (const rider of riders) {
            if (!rider.isValid || rider.typeId !== 'gc:archer') continue;
            if ((rider.getComponent('minecraft:health')?.currentValue ?? 1) <= 0) continue;
            const slot = rider.getDynamicProperty('gc:crew_slot');
            if ((slot === 0 || slot === 1) && !slots[slot]) slots[slot] = rider;
            else pending.push(rider);
          }
          for (const rider of pending) {
            const slot = slots.findIndex(value => !value);
            if (slot < 0) break;
            slots[slot] = rider;
            rider.setDynamicProperty('gc:crew_slot', slot);
          }
          for (let slot = 0; slot < 2; slot++) {
            const rider = slots[slot];
            const side = SIDES[slot];
            const rotation = rider?.getRotation() ?? { x: 0, y: 0 };
            const yaw = rider ? wrapAngle(rotation.y - giant.getRotation().y) : 0;
            setChanged(giant, 'gc:' + side + '_yaw', Math.round(clamp(yaw, 70)));
            setChanged(giant, 'gc:' + side + '_pitch', Math.round(clamp(rotation.x, 35)));
            setChanged(giant, 'gc:crew_' + side, !!rider);
            if (rider) represented.add(rider.id);
          }
        } catch (error) { warn('Crew sync', error); }
      }
      // Dismounted/orphaned riders regain their own mesh and normal scale,
      // including after carrier death, removal, save/reload or riding another mob.
      for (const rider of dimension.getEntities({ type: 'gc:archer' })) {
        try { setPacked(rider, represented.has(rider.id)); }
        catch (error) { warn('Rider visibility', error); }
      }
    } catch (error) { warn('Dimension sync', error); }
  }
}, 2);
