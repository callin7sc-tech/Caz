import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm';

const source = readFileSync(new URL('../minecraft/colossus.js', import.meta.url), 'utf8');
const GameMode = { Creative: 'Creative', Spectator: 'Spectator', Survival: 'Survival', Adventure: 'Adventure' };
async function fixture() {
  const particles = [], sounds = [], warnings = [];
  const dimension = {
    id: 'overworld', entities: [], rayHits: [], wall: undefined,
    getEntities(options = {}) {
      return this.entities.filter(e => (!options.type || e.typeId === options.type) &&
        (!options.location || Math.hypot(e.location.x-options.location.x,e.location.y-options.location.y,e.location.z-options.location.z) <= options.maxDistance));
    },
    getBlockFromRay(origin, direction, options) {
      assert.equal(options.includeLiquidBlocks, false);
      assert.equal(options.includePassableBlocks, false);
      if (this.wall === undefined || this.wall > options.maxDistance) return;
      return { block: { location: { x: origin.x+direction.x*this.wall, y: origin.y+direction.y*this.wall, z: origin.z+direction.z*this.wall } }, faceLocation: { x:0,y:0,z:0 } };
    },
    getEntitiesFromRay(origin, direction, options) {
      assert.equal(options.ignoreBlockCollision, false);
      assert.equal(options.excludeTypes[0], 'gc:robot_colossus');
      return this.rayHits.filter(h => h.distance <= options.maxDistance);
    },
    spawnParticle(name, position) { particles.push({name,position}); },
    playSound(name) { sounds.push(name); },
  };
  let serial = 0;
  function entity(type='minecraft:zombie', position={x:0,y:0,z:12}, families=['monster']) {
    return {
      id: 'entity'+(++serial), typeId:type, location:position, isValid:true, isOnGround:true,
      dimension, hp:600, mode:GameMode.Survival, rotation:{x:0,y:0}, properties:{}, damage:[], knockback:[], events:[],
      getComponent(name) {
        if (name === 'minecraft:health') return {currentValue:this.hp};
        if (name === 'minecraft:type_family') return {hasTypeFamily: f => families.includes(f)};
      },
      getGameMode() { return this.mode; },
      getHeadLocation() { return {...this.location,y:this.location.y+1.6}; },
      getRotation() { return this.rotation; },
      setRotation(value) { this.rotation=value; },
      getProperty(key) { return this.properties[key]; },
      setProperty(key,value) { this.properties[key]=value; },
      triggerEvent(name) { this.events.push(name); },
      applyDamage(amount, options) { this.damage.push({amount,options}); this.hp-=amount; return true; },
      applyKnockback(horizontal, vertical) { this.knockback.push({horizontal,vertical}); },
    };
  }
  const system = { currentTick:0, runInterval(fn,n) { assert.equal(n,2); this.interval=fn; } };
  const world = {getDimension: id => id === 'overworld' ? dimension : {...dimension,id,entities:[]}};
  const context = createContext({console:{warn: x => warnings.push(x)}});
  const mock = new SyntheticModule(['world','system','EntityDamageCause','GameMode'], function() {
    this.setExport('world',world); this.setExport('system',system);
    this.setExport('EntityDamageCause',{entityAttack:'entityAttack'}); this.setExport('GameMode',GameMode);
  }, {context});
  const module = new SourceTextModule(source,{context});
  await module.link(() => mock); await module.evaluate();
  const api = module.namespace;
  const robot = entity(api.ROBOT,{x:0,y:0,z:0},['robot_colossus','monster']);
  const target = entity(); dimension.entities=[robot,target];
  dimension.rayHits=[{entity:target,distance:10}];
  const tick = n => {system.currentTick=n; api.update();};
  const shot = {yaw:0,pitch:20,point:{x:0,y:1.4,z:12}};
  return {api,entity,dimension,robot,target,tick,shot,particles,sounds,warnings};
}

test('targets players, monsters and both goblin families, not passives or robots', async () => {
  const f=await fixture();
  for (const [type,families,wanted] of [
    ['minecraft:player',[],true],['minecraft:zombie',['monster'],true],
    ['gc:archer',['goblin_caravan'],true],['gc:giant',['goblin_caravan'],true],
    ['other:goblin',['goblin'],true],['minecraft:cow',['animal'],false],
    [f.api.ROBOT,['monster'],false],['minecraft:item',[],false],
  ]) assert.equal(f.api.isTarget(f.entity(type,undefined,families)),wanted,type);
});
test('creative and spectator excluded; adventure and survival allowed', async () => {
  const f=await fixture(), p=f.entity('minecraft:player');
  for (const mode of Object.values(GameMode)) {
    p.mode=mode;
    assert.equal(f.api.isTarget(p),mode==='Survival'||mode==='Adventure');
  }
  p.isValid=false; assert.equal(f.api.isTarget(p),false);
  f.target.hp=0; assert.equal(f.api.isTarget(f.target),false);
});
test('laser deals one hit across two eyes, with robot attribution', async () => {
  const f=await fixture(); f.api.fireLaser(f.robot,f.shot);
  assert.equal(f.target.damage.length,1); assert.equal(f.target.damage[0].amount,16);
  assert.equal(f.target.damage[0].options.damagingEntity,f.robot);
  assert.equal(f.particles.filter(p=>p.name==='gc:colossus_spark').length,2);
});
test('walls stop laser damage and clip all beam particles', async () => {
  const f=await fixture(); f.dimension.wall=3; f.api.fireLaser(f.robot,f.shot);
  assert.equal(f.target.damage.length,0);
  assert.ok(f.particles.every(p=>p.position.z<4));
});
test('passive first body intercepts but takes no damage', async () => {
  const f=await fixture(), cow=f.entity('minecraft:cow',undefined,['animal']);
  f.dimension.rayHits.push({entity:cow,distance:3}); f.api.fireLaser(f.robot,f.shot);
  assert.equal(cow.damage.length,0); assert.equal(f.target.damage.length,0);
});
test('ray hits are sorted; dead bodies do not shield targets', async () => {
  const f=await fixture(), corpse=f.entity(); corpse.hp=0;
  const nearer=f.entity(); f.dimension.rayHits.push({entity:corpse,distance:1},{entity:nearer,distance:5});
  f.api.fireLaser(f.robot,f.shot); assert.equal(nearer.damage.length,1); assert.equal(f.target.damage.length,0);
});
test('range and particle budget are bounded', async () => {
  const f=await fixture(); f.dimension.rayHits=[{entity:f.target,distance:29}];
  f.api.fireLaser(f.robot,f.shot); assert.equal(f.target.damage.length,0);
  assert.ok(f.particles.length<=192);
});
test('eye offsets rotate with yaw and pitch around model head pivot', async () => {
  const f=await fixture();
  const eyes=f.api.eyeOrigins(f.robot,0,0);
  assert.equal(eyes[0].y,117/16); assert.equal(eyes[0].z,13/16);
  assert.equal(eyes[1].x-eyes[0].x,12/16);
  for (const yaw of [-180,-90,0,90,180]) {
    const pair=f.api.eyeOrigins(f.robot,yaw,40);
    assert.ok(Math.abs(Math.hypot(pair[0].x-pair[1].x,pair[0].z-pair[1].z)-.75)<1e-9);
    assert.ok(pair[0].y<117/16);
  }
});
test('stomp hits ground targets once and uses stable 2.0 knockback signature', async () => {
  const f=await fixture(); f.target.location={x:1,y:0,z:2};
  f.api.stomp(f.robot,f.shot);
  assert.equal(f.target.damage.length,1); assert.equal(f.target.damage[0].amount,24);
  assert.equal(f.target.knockback[0].vertical,.55);
  assert.ok(Number.isFinite(f.target.knockback[0].horizontal.x));
  assert.equal(f.robot.damage.length,0); assert.equal(f.particles.length,72);
});
test('stomp excludes airborne, distant, passive, creative and wall-shielded victims', async () => {
  const f=await fixture();
  const victims=[f.entity('minecraft:zombie',{x:1,y:4,z:1}),f.entity('minecraft:zombie',{x:6,y:0,z:0}),
    f.entity('minecraft:cow',{x:1,y:0,z:1},['animal']),f.entity('minecraft:player',{x:1,y:0,z:1})];
  victims[3].mode=GameMode.Creative; f.dimension.entities.push(...victims);
  f.api.stomp(f.robot,f.shot); assert.ok(victims.every(e=>e.damage.length===0));
  f.target.location={x:1,y:0,z:2}; f.dimension.wall=.2;
  f.api.stomp(f.robot,f.shot); assert.equal(f.target.damage.length,0);
});
test('stomp does not knock back an invulnerable victim', async () => {
  const f=await fixture(); f.target.location={x:1,y:0,z:2}; f.target.applyDamage=()=>false;
  f.api.stomp(f.robot,f.shot); assert.equal(f.target.knockback.length,0);
});
test('laser winds up for 20 ticks, fires once, then resumes walking', async () => {
  const f=await fixture(); f.tick(0); f.tick(20);
  assert.equal(f.robot.properties['gc:action'],'laser');
  for(let t=22;t<40;t+=2) f.tick(t);
  assert.equal(f.target.damage.length,0); f.tick(40);
  assert.equal(f.target.damage.length,1);
  for(let t=42;t<=60;t+=2) f.tick(t);
  assert.equal(f.target.damage.length,1); assert.equal(f.robot.properties['gc:action'],'idle');
  assert.equal(f.robot.events.at(-1),'gc:colossus_resume');
});
test('laser cooldown prevents early repeated attacks', async () => {
  const f=await fixture(); for(let t=0;t<=88;t+=2) f.tick(t);
  assert.equal(f.target.damage.length,1); assert.equal(f.robot.properties['gc:action'],'idle');
  f.tick(90); assert.equal(f.robot.properties['gc:action'],'laser');
});
test('stomp impact is at tick 16, not during lift', async () => {
  const f=await fixture(); f.target.location={x:1,y:0,z:2}; f.tick(0); f.tick(20);
  assert.equal(f.robot.properties['gc:action'],'stomp'); f.tick(34);
  assert.equal(f.target.damage.length,0); f.tick(36); assert.equal(f.target.damage[0].amount,24);
  f.tick(38); assert.equal(f.target.damage.length,1); f.tick(52);
  assert.equal(f.robot.properties['gc:action'],'idle');
});
test('losing ground before stomp impact cancels the damage', async () => {
  const f=await fixture(); f.target.location={x:1,y:0,z:2}; f.tick(0); f.tick(20);
  f.robot.isOnGround=false; f.tick(36); assert.equal(f.target.damage.length,0);
});
test('removed target or dimension change cancels charged laser', async () => {
  for(const changedDimension of [false,true]) {
    const f=await fixture(); f.tick(0); f.tick(20);
    if(changedDimension) f.target.dimension={id:'nether'}; else f.target.isValid=false;
    f.tick(22); assert.equal(f.robot.properties['gc:action'],'idle'); assert.equal(f.target.damage.length,0);
  }
});
test('mode change during windup cancels aggression', async () => {
  const f=await fixture(); f.target.typeId='minecraft:player'; f.tick(0); f.tick(20);
  f.target.mode=GameMode.Creative; f.tick(30); assert.equal(f.robot.properties['gc:action'],'idle');
});
test('reload and unloaded-chunk re-entry clear frozen persisted state', async () => {
  const f=await fixture(); f.robot.properties['gc:action']='stomp'; f.tick(0);
  assert.equal(f.robot.properties['gc:action'],'idle');
  f.tick(20); f.dimension.entities=[]; f.tick(22);
  f.dimension.entities=[f.robot,f.target]; f.tick(40);
  assert.equal(f.robot.properties['gc:action'],'idle'); assert.equal(f.target.damage.length,0);
});
test('suspended updates do not replay a stale attack', async () => {
  const f=await fixture(); f.tick(0); f.tick(20); f.tick(120);
  assert.equal(f.target.damage.length,0); assert.equal(f.robot.properties['gc:action'],'idle');
});
test('multiple colossi maintain independent attack state', async () => {
  const f=await fixture(), second=f.entity(f.api.ROBOT,{x:3,y:0,z:0},['monster']);
  f.dimension.entities.push(second); f.tick(0); f.tick(20); f.tick(40);
  assert.equal(f.target.damage.length,2);
  assert.notEqual(f.target.damage[0].options.damagingEntity.id,f.target.damage[1].options.damagingEntity.id);
});
test('cosmetic particle errors never cancel damage or recovery', async () => {
  const f=await fixture(); f.dimension.spawnParticle=()=>{throw new Error('unloaded chunk');};
  f.tick(0); f.tick(20); f.tick(40); f.tick(60);
  assert.equal(f.target.damage.length,1); assert.equal(f.robot.properties['gc:action'],'idle');
  assert.equal(f.warnings.length,1);
});
test('dead robots cannot finish pending attacks', async () => {
  const f=await fixture(); f.tick(0); f.tick(20); f.robot.hp=0; f.tick(40);
  assert.equal(f.target.damage.length,0);
});

// Regression: the original tests only used even world ticks, masking total starvation.
test('combat works from every scheduler phase, including odd ticks', async () => {
  for (let phase=0; phase<10; phase++) {
    const f=await fixture();
    for(let t=phase;t<=phase+60;t+=2) f.tick(t);
    assert.equal(f.target.damage.length,1,`scheduler phase ${phase}`);
    assert.equal(f.robot.properties['gc:action'],'idle');
  }
});
test('irregular update cadence still acquires and attacks', async () => {
  const f=await fixture();
  for(const t of [3,8,17,24,31,39,45,51,65]) f.tick(t);
  assert.equal(f.target.damage.length,1);
  assert.equal(f.robot.properties['gc:action'],'idle');
});
test('robot turns in bounded steps before charging behind its back', async () => {
  const f=await fixture(); f.target.location.z=-12;
  let previous=0;
  for(let t=1;t<100;t+=2) {
    f.tick(t);
    const yaw=f.robot.getRotation().y;
    const delta=((yaw-previous+540)%360)-180;
    assert.ok(Math.abs(delta)<=f.api.CONFIG.turnStep+1e-8);
    previous=yaw;
    if(t<49) assert.equal(f.target.damage.length,0);
  }
  assert.equal(f.target.damage.length,1);
});
test('crossing the yaw boundary takes the short arc', async () => {
  const f=await fixture(); f.robot.rotation.y=179;
  f.target.location={x:.2,y:0,z:-12}; f.tick(0); f.tick(20);
  const yaw=f.robot.properties['gc:aim_yaw'];
  assert.ok(Math.abs(((yaw-179+540)%360)-180)<3);
});
test('invalid entity handles cannot prevent other targets being attacked', async () => {
  const f=await fixture(), broken=f.entity();
  broken.getComponent=()=>{throw new Error('InvalidEntityError');};
  f.dimension.entities.push(broken);
  f.tick(1); f.tick(21); f.tick(41);
  assert.equal(f.target.damage.length,1);
});
test('stomp is cancelled when the target switches to creative during windup', async () => {
  const f=await fixture(); f.target.typeId='minecraft:player'; f.target.location={x:1,y:0,z:2};
  f.tick(1); f.tick(21); f.target.mode=GameMode.Creative; f.tick(23); f.tick(37);
  assert.equal(f.target.damage.length,0); assert.equal(f.robot.properties['gc:action'],'idle');
});
test('a rejected laser hit does not suppress both beams or recovery', async () => {
  const f=await fixture(); f.target.applyDamage=()=>{throw new Error('InvalidEntityError');};
  f.tick(0); f.tick(20); f.tick(40); f.tick(60);
  assert.ok(f.particles.filter(p=>p.name==='gc:colossus_laser').length>20);
  assert.equal(f.robot.properties['gc:action'],'idle');
});
test('laser lock stops tracking four ticks before firing', async () => {
  const f=await fixture(); f.tick(0); f.tick(20); f.tick(34);
  const yaw=f.robot.properties['gc:aim_yaw'];
  f.target.location.x=5; f.tick(36); f.tick(38);
  assert.equal(f.robot.properties['gc:aim_yaw'],yaw);
});

test('suspension while turning cannot resume a stale attack', async () => {
  const f=await fixture(); f.target.location.z=-12;
  f.tick(1); f.tick(21); f.tick(101);
  assert.equal(f.robot.properties['gc:action'],'idle');
  assert.equal(f.target.damage.length,0);
  assert.equal(f.robot.events.at(-1),'gc:colossus_resume');
});
