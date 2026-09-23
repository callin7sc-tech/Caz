"""Run: python -B tests/test_colossus_assets.py. No Minecraft runtime required."""
import base64
import io
import json
import math
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BP = 'addon-source/Goblin_Caravan_BP/'
RP = 'addon-source/Goblin_Caravan_RP/'

class ClientSignals:
    """Evaluate only the arithmetic/boolean Molang subset emitted by this builder.

    This is a regression harness for our expressions, NOT a Minecraft renderer or
    a general Molang validator. Temporaries are reset between script expressions.
    """
    def __init__(self, client, position=(0, 0, 0), properties=None):
        self.scripts = client['scripts']
        self.properties = dict(properties or {})
        self.xyz = list(position)
        self.variable = SimpleNamespace()
        self.temp = SimpleNamespace()
        self.query = SimpleNamespace(
            position=lambda axis: self.xyz[axis], health=600, delta_time=1/60,
            is_on_ground=True, anim_time=0,
            has_property=lambda key: key in self.properties,
            property=lambda key: self.properties[key])
        self.functions = SimpleNamespace(
            sqrt=math.sqrt, max=max, min=min, mod=lambda a, b: a % b,
            lerp=lambda a, b, t: a+(b-a)*t,
            sin=lambda degrees: math.sin(math.radians(degrees)))
        self.run(self.scripts['initialize'])

    def evaluate(self, expression):
        if '?' in expression:
            condition, branches = expression.split('?', 1)
            yes, no = branches.split(' : ', 1)
            return self.evaluate(yes if self.evaluate(condition) else no)
        expression = expression.replace('&&', ' and ').replace('||', ' or ')
        expression = re.sub(r'!(?!=)', ' not ', expression).strip()
        return eval(expression, {'__builtins__': {}}, {
            'variable': self.variable, 'temp': self.temp,
            'query': self.query, 'math': self.functions})

    def run(self, scripts):
        for script in scripts:
            self.temp = SimpleNamespace()
            for statement in script.split(';'):
                if not statement.strip(): continue
                target, expression = statement.strip().split(' = ', 1)
                namespace, name = target.split('.')
                setattr(getattr(self, namespace), name, self.evaluate(expression))

    def frame(self, dx=0, dz=0, dt=1/60, ground=True, health=None):
        self.xyz[0] += dx; self.xyz[2] += dz
        self.query.delta_time = dt; self.query.is_on_ground = ground
        if health is not None: self.query.health = health
        self.run(self.scripts['pre_animation'])

    def transition(self, states, state):
        for transition in states[state].get('transitions', []):
            target, condition = next(iter(transition.items()))
            if self.evaluate(condition): return target
        return state


class Assets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.z = zipfile.ZipFile(ROOT/'Goblin-Caravan-Blockbench.zip')
        cls.a = zipfile.ZipFile(ROOT/'Goblin-Caravan.mcaddon')
        cls.geo = json.loads(cls.z.read('geometry/robot_colossus.geo.json'))['minecraft:geometry'][0]
        cls.bb = json.loads(cls.z.read('robot_colossus.bbmodel'))
        cls.anim = json.loads(cls.z.read('animations/colossus.animation.json'))['animations']
        cls.behavior = json.loads(cls.z.read(BP+'entities/robot_colossus.json'))['minecraft:entity']
        cls.client = json.loads(cls.z.read(RP+'entity/robot_colossus.entity.json'))['minecraft:client_entity']['description']
        cls.controllers = json.loads(cls.z.read(RP+'animation_controllers/colossus.json'))['animation_controllers']

    @classmethod
    def tearDownClass(cls):
        cls.z.close(); cls.a.close()

    def test_archives_and_all_json(self):
        for z in [self.z,self.a]:
            self.assertIsNone(z.testzip())
            self.assertEqual(len(z.namelist()),len(set(z.namelist())))
            for n in z.namelist():
                self.assertNotIn('..',Path(n).parts)
                self.assertFalse(n.startswith('/'))
                if n.endswith(('.json','.bbmodel')): json.loads(z.read(n))

    def test_packs_match_editable_source_exactly(self):
        for name,prefix in [('Goblin_Caravan_BP.mcpack',BP),('Goblin_Caravan_RP.mcpack',RP)]:
            with zipfile.ZipFile(io.BytesIO(self.a.read(name))) as pack:
                self.assertIsNone(pack.testzip())
                expected={n[len(prefix):] for n in self.z.namelist() if n.startswith(prefix)}
                self.assertEqual(set(pack.namelist()),expected)
                for n in pack.namelist(): self.assertEqual(pack.read(n),self.z.read(prefix+n))
        self.assertEqual(self.a.read('LEGGIMI.txt'),self.z.read('LEGGIMI.txt'))

    def test_height_uv_bounds_and_parent_graph(self):
        bones={b['name']:b for b in self.geo['bones']}
        self.assertEqual(len(bones),len(self.geo['bones']))
        cubes=[c for b in bones.values() for c in b['cubes']]
        self.assertEqual(min(c['origin'][1] for c in cubes),0)
        self.assertEqual(max(c['origin'][1]+c['size'][1] for c in cubes),128)
        self.assertEqual(self.behavior['components']['minecraft:collision_box']['height'],8)
        for b in bones.values():
            ancestors=set(); parent=b
            while 'parent' in parent:
                self.assertNotIn(parent['name'],ancestors); ancestors.add(parent['name'])
                parent=bones[parent['parent']]
        for c in cubes:
            self.assertTrue(all(x>0 for x in c['size']))
            for face in c['uv'].values():
                for origin,size in zip(face['uv'],face['uv_size']):
                    self.assertGreaterEqual(origin,0); self.assertLessEqual(origin+size,256)

    def test_blockbench_coordinates_and_uv_roundtrip(self):
        elements={e['name']:e for e in self.bb['elements']}
        for b in self.geo['bones']:
            for i,c in enumerate(b['cubes']):
                e=elements[b['name']+'_'+str(i)]
                f,t=e['from'],e['to']
                self.assertEqual([-t[0],f[1],f[2]],c['origin'])
                self.assertEqual([t[j]-f[j] for j in range(3)],c['size'])
                for name,uv in c['uv'].items():
                    a=e['faces'][name]['uv']; a=[a[2],a[3],a[0],a[1]] if name in ['up','down'] else a
                    self.assertEqual(a[:2],uv['uv'])

                    for got,wanted in zip([a[2]-a[0],a[3]-a[1]],uv['uv_size']):
                        self.assertAlmostEqual(got,wanted)

    def test_blockbench_hierarchy_and_embedded_texture(self):
        elements={e['uuid'] for e in self.bb['elements']}; referenced=[]; groups={}
        def walk(g,parent=None):
            groups[g['name']]=(g,parent)
            for child in g['children']:
                if isinstance(child,dict): walk(child,g['name'])
                else: referenced.append(child)
        for root in self.bb['outliner']: walk(root)
        self.assertEqual(set(referenced),elements); self.assertEqual(len(referenced),len(elements))
        for b in self.geo['bones']:
            g,parent=groups[b['name']]
            self.assertEqual(parent,b.get('parent'))
            self.assertEqual(g['origin'],[-b['pivot'][0],*b['pivot'][1:]])
        png=self.z.read('textures/robot_colossus.png')
        self.assertEqual(base64.b64decode(self.bb['textures'][0]['source'].split(',')[1]),png)
        self.assertEqual(Image.open(io.BytesIO(png)).size,(256,256))
        image=Image.open(io.BytesIO(png)).convert('RGBA')
        # Violet armour everywhere except the red reactor/lens column (x 160-191).
        for x in range(256):
            for y in range(256):
                r,g,b,a=image.getpixel((x,y))
                if 160<=x<192: self.assertTrue(r>=g and r>=b, (x,y))
                else: self.assertTrue(b>=r>g, (x,y))
        r,g,b,a=image.getpixel((164,16)); self.assertGreater(r,200); self.assertLess(b,170)

    def test_animations_bones_and_damage_keyframes(self):
        names={b['name'] for b in self.geo['bones']}
        self.assertEqual(len(self.anim),7)
        self.assertEqual({a['name'] for a in self.bb['animations']},set(self.anim))
        for a in self.anim.values(): self.assertTrue(set(a['bones'])<=names)
        for action in ['stomp','laser']:
            a=self.anim['animation.gc.colossus.'+action]
            self.assertEqual(a['anim_time_update'],"query.property('gc:attack_tick') / 20.0")
        stomp=self.anim['animation.gc.colossus.stomp']
        for b in ['leg_right','shin_right','foot_right']:
            self.assertEqual(stomp['bones'][b]['rotation']['0.8'],[0,0,0])
        self.assertIn('1.0',self.anim['animation.gc.colossus.laser']['bones']['eye_left']['scale'])
        self.assertGreater(self.anim['animation.gc.colossus.laser']['bones']['reactor']['scale']['1.0'][2],2)

    def test_red_laser_particles_and_native_combat(self):
        laser=json.loads(self.z.read(RP+'particles/colossus_laser.json'))['particle_effect']['components']
        r,g,b,_=laser['minecraft:particle_appearance_tinting']['color']
        self.assertEqual(r,1); self.assertLess(g,.2); self.assertLess(b,.2)
        c=self.behavior['components']
        self.assertGreaterEqual(c['minecraft:attack']['damage'],20)
        self.assertIn('minecraft:behavior.melee_box_attack',self.behavior['component_groups']['gc:mobile'])
        self.assertIn('minecraft:behavior.hurt_by_target',c)
        text=json.dumps(c['minecraft:behavior.nearest_attackable_target'])
        for family in ['monster','goblin_caravan','goblin_giant','goblin_archer','player']: self.assertIn(family,text)
        self.assertIn('laser rosso',json.loads(self.z.read(BP+'manifest.json'))['header']['description'])

    def test_manifest_identity_version_and_script_import(self):
        b=json.loads(self.z.read(BP+'manifest.json')); r=json.loads(self.z.read(RP+'manifest.json'))
        ids=[]
        for m in [b,r]:
            self.assertEqual(m['header']['version'],[1,2,3]); ids.append(m['header']['uuid'])
            for mod in m['modules']:
                ids.append(mod['uuid']); self.assertEqual(mod['version'],[1,2,3])
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn({'uuid':r['header']['uuid'],'version':[1,2,3]},b['dependencies'])
        self.assertIn({'module_name':'@minecraft/server','version':'2.0.0'},b['dependencies'])
        self.assertEqual(self.z.read(BP+'scripts/colossus.js'),(ROOT/'minecraft/colossus.js').read_bytes())
        self.assertEqual(self.z.read(BP+'scripts/main.js').count(b"import './colossus.js';"),1)

    def test_sync_properties_and_controller_references(self):
        properties=self.behavior['description']['properties']
        for p in properties.values(): self.assertTrue(p['client_sync'])
        client=json.loads(self.z.read(RP+'entity/robot_colossus.entity.json'))['minecraft:client_entity']['description']
        controller=json.loads(self.z.read(RP+'animation_controllers/colossus.json'))['animation_controllers']
        for name in client['animations'].values(): self.assertTrue(name in self.anim or name in controller)
        for value in [self.anim,client,controller]:
            for prop in re.findall(r"query.property\('([^']+)'\)",json.dumps(value)):
                self.assertIn(prop,properties)
        self.assertEqual(self.z.read(RP+'models/entity/robot_colossus.geo.json'),self.z.read('geometry/robot_colossus.geo.json'))
        self.assertEqual(self.z.read(RP+'animations/colossus.animation.json'),self.z.read('animations/colossus.animation.json'))

    def test_original_goblins_preserved(self):
        original=subprocess.check_output(['git','show','fd77d52:Goblin-Caravan-Blockbench.zip'],cwd=ROOT)
        allowed={'LEGGIMI.txt','addon-source/LEGGIMI.txt',BP+'manifest.json',RP+'manifest.json',
                 BP+'scripts/main.js',RP+'texts/it_IT.lang',RP+'texts/en_US.lang'}
        with zipfile.ZipFile(io.BytesIO(original)) as old:
            for n in old.namelist():
                if n not in allowed: self.assertEqual(old.read(n),self.z.read(n),n)
            self.assertEqual(old.read(BP+'scripts/main.js'),self.z.read(BP+'scripts/main.js').replace(b"import './colossus.js';\n",b''))

    def test_walk_feet_are_level_and_do_not_sink_into_floor(self):
        walk=self.anim['animation.gc.colossus.walk']
        self.assertEqual(walk['anim_time_update'],'variable.gc_walk_phase')
        for side in ['left','right']:
            keys=walk['bones']['leg_'+side]['rotation']
            for time,hip in keys.items():
                knee=walk['bones']['shin_'+side]['rotation'][time][0]
                foot=walk['bones']['foot_'+side]['rotation'][time][0]
                a,b=map(math.radians,[hip[0],hip[0]+knee])
                sole_y=62-28*math.cos(a)-26*math.cos(b)-10
                self.assertGreaterEqual(sole_y,-.0001)
                self.assertLessEqual(sole_y,7.0001)
                self.assertAlmostEqual(hip[0]+knee+foot,0,places=4)
            self.assertEqual(keys['0.0'],keys['1.0'])

    def test_locomotion_states_blend_and_stop_during_combat(self):
        controllers=json.loads(self.z.read(RP+'animation_controllers/colossus.json'))['animation_controllers']
        states=controllers['controller.animation.gc.colossus.locomotion']['states']
        self.assertEqual(set(states),{'idle','walk','air','combat'})
        self.assertNotIn('animations',states['combat'])
        for state in states.values():
            self.assertGreater(state['blend_transition'],0)
            for transition in state['transitions']:
                self.assertTrue(set(transition)<=set(states))
        aim=self.anim['animation.gc.colossus.aim']['bones']['root']['rotation'][1]
        self.assertIn('math.min_angle',aim)

    def test_native_navigation_and_targeting_are_stable(self):
        mobile=self.behavior['component_groups']['gc:mobile']
        self.assertEqual(mobile['minecraft:behavior.move_towards_target']['within_radius'],3)
        self.assertFalse(self.behavior['components']['minecraft:behavior.nearest_attackable_target']['reselect_targets'])
        self.assertTrue(self.behavior['components']['minecraft:navigation.walk']['avoid_damage_blocks'])
        self.assertEqual(self.behavior['component_groups']['gc:frozen']['minecraft:movement']['value'],0)

    def test_basic_animation_has_no_vanilla_runtime_or_script_dependency(self):
        self.assertNotIn('runtime_identifier', self.behavior['description'])
        self.assertEqual(self.client['min_engine_version'], '1.21.90')
        self.assertEqual(self.client['scripts']['animate'][:2], ['idle', 'locomotion'])
        signals = ClientSignals(self.client, position=(1000, 70, -1000))
        signals.frame()
        self.assertFalse(signals.variable.gc_combat)
        self.assertEqual(signals.variable.gc_speed, 0)
        self.assertEqual(signals.variable.gc_walk_phase, 0)
        # Missing/late properties must not suppress all locomotion.
        for action in [None, 'idle', 'invalid']:
            signals.properties = {} if action is None else {'gc:action': action}
            signals.frame(dx=.1)
            self.assertFalse(signals.variable.gc_combat)
        for controller in self.controllers.values():
            for state in controller['states'].values():
                self.assertNotIn('idle', state.get('animations', []))
        idle = self.anim['animation.gc.colossus.idle']
        signals.query.anim_time = 0
        before = signals.evaluate(idle['bones']['forearm_left']['rotation'][0])
        signals.query.anim_time = 1
        self.assertNotEqual(before, signals.evaluate(idle['bones']['forearm_left']['rotation'][0]))

    def test_walk_clock_advances_for_many_cycles_at_different_frame_rates(self):
        for fps in [20, 30, 60, 144]:
            signals = ClientSignals(self.client)
            clock = self.anim['animation.gc.colossus.walk']['anim_time_update']
            # No modified_move_speed / modified_distance_moved in this fixture.
            for frame in range(fps*12):
                signals.frame(dz=2/fps, dt=1/fps)
                phase = signals.evaluate(clock)
                self.assertGreaterEqual(phase, 0)
                self.assertLess(phase, 1)
                expected = ((frame+1)*2/fps/2.5) % 1
                # Phase 1-epsilon and phase 0 describe the same looping pose.
                self.assertAlmostEqual((phase-expected+.5) % 1-.5, 0, places=7)
            self.assertAlmostEqual(signals.variable.gc_speed, 2, places=5)
            saved = signals.variable.gc_walk_phase
            for _ in range(fps): signals.frame(dt=1/fps)
            self.assertEqual(signals.variable.gc_walk_phase, saved)
            self.assertLess(signals.variable.gc_speed, .02)

    def test_teleport_air_and_combat_do_not_advance_walk_phase(self):
        signals = ClientSignals(self.client)
        signals.frame(dx=.5)
        phase = signals.variable.gc_walk_phase
        for options in [dict(dx=100), dict(dz=.2, ground=False), dict(dx=.2, dt=0)]:
            signals.frame(**options)
            self.assertEqual(signals.variable.gc_walk_phase, phase)
        for action in ['laser', 'stomp']:
            signals.properties['gc:action'] = action
            signals.frame(dx=.2)
            self.assertEqual(signals.variable.gc_walk_phase, phase)
        signals.properties['gc:action'] = 'idle'
        signals.frame(dx=.1)
        self.assertAlmostEqual(signals.variable.gc_walk_phase, phase+.1/2.5)

    def test_client_hurt_pulse_works_without_hurt_time_query(self):
        signals = ClientSignals(self.client)
        signals.frame(health=590)
        self.assertEqual(signals.variable.gc_hurt_remaining, .5)
        condition = self.client['scripts']['animate'][2]['hurt']
        self.assertTrue(signals.evaluate(condition))
        signals.frame(dt=.25)
        expression = self.anim['animation.gc.colossus.hurt']['bones']['torso']['rotation'][0]
        self.assertAlmostEqual(signals.evaluate(expression), -3)
        signals.properties['gc:action'] = 'laser'
        signals.frame()
        self.assertFalse(signals.evaluate(condition))
        signals.properties['gc:action'] = 'idle'
        signals.frame(dt=.5)
        self.assertFalse(signals.evaluate(condition))
        signals.frame(health=600)
        self.assertFalse(signals.evaluate(condition))
        signals.frame(health=580)
        self.assertTrue(signals.evaluate(condition))

    def test_client_state_transitions_and_repeated_combat(self):
        signals = ClientSignals(self.client)
        states = self.controllers['controller.animation.gc.colossus.locomotion']['states']
        signals.frame(dx=.1)
        self.assertEqual(signals.transition(states, 'idle'), 'walk')
        signals.frame(ground=False)
        self.assertEqual(signals.transition(states, 'walk'), 'air')
        signals.frame(dt=1)
        self.assertEqual(signals.transition(states, 'air'), 'idle')
        combat = self.controllers['controller.animation.gc.colossus']['states']
        for action, hit in [('laser', 20), ('stomp', 16)] * 3:
            signals.properties.update({'gc:action': action, 'gc:attack_tick': 0})
            signals.frame()
            self.assertEqual(signals.transition(states, 'walk'), 'combat')
            self.assertEqual(signals.transition(combat, 'idle'), action)
            clock = self.anim['animation.gc.colossus.'+action]['anim_time_update']
            self.assertEqual(signals.evaluate(clock), 0)
            signals.properties['gc:attack_tick'] = hit
            self.assertEqual(signals.evaluate(clock), hit/20)
            signals.properties['gc:action'] = 'idle'
            signals.frame()
            self.assertEqual(signals.transition(states, 'combat'), 'idle')
            self.assertEqual(signals.transition(combat, action), 'idle')

    def test_all_animation_aliases_are_reachable_and_all_bones_resolve(self):
        aliases = self.client['animations']
        visited = set()
        def visit(entry):
            name = entry if isinstance(entry, str) else next(iter(entry))
            self.assertIn(name, aliases)
            if name in visited: return
            visited.add(name)
            resource = aliases[name]
            if resource in self.controllers:
                controller = self.controllers[resource]
                self.assertIn(controller['initial_state'], controller['states'])
                for state in controller['states'].values():
                    for animation in state.get('animations', []): visit(animation)
            else:
                self.assertIn(resource, self.anim)
        for entry in self.client['scripts']['animate']: visit(entry)
        self.assertEqual(visited, set(aliases))
        for animation in self.anim.values():
            self.assertTrue(set(animation['bones']) <= {bone['name'] for bone in self.geo['bones']})

    def test_reproducible_build(self):
        paths=[ROOT/'Goblin-Caravan.mcaddon',ROOT/'Goblin-Caravan-Blockbench.zip']
        before=[p.read_bytes() for p in paths]
        subprocess.run([sys.executable,'-B',str(ROOT/'minecraft/build_colossus.py')],cwd=ROOT,check=True)
        self.assertEqual(before,[p.read_bytes() for p in paths])

if __name__=='__main__': unittest.main(verbosity=2)
