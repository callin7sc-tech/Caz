#!/usr/bin/env python3
"""Build original robot assets and update both existing archives without touching goblins.
Run from any directory: python minecraft/build_colossus.py (requires Pillow).
The existing Blockbench archive supplies unchanged caravan assets. Output is deterministic.
"""
import base64
import io
import json
import math
import random
import uuid
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BP = 'addon-source/Goblin_Caravan_BP/'
RP = 'addon-source/Goblin_Caravan_RP/'
VERSION = [1, 2, 3]
FACES = ['north', 'south', 'east', 'west', 'up', 'down']
BONES = []


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'gc:robot_colossus/' + name))


def archive(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, value in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 21, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, value)
    return buf.getvalue()


def texture():
    """256px atlas: bevelled violet metal, joints, vents, reactor, circuits and tread."""
    rng = random.Random(84321)
    im = Image.new('RGBA', (256, 256), (27, 12, 46, 255))
    d = ImageDraw.Draw(im)
    palette = [(102, 44, 168), (159, 84, 216), (42, 20, 67), (71, 37, 100),
               (51, 26, 78), (200, 24, 16), (91, 40, 146), (47, 25, 66)]
    for row in range(8):
        shade = [1.0, .85, .92, .95, 1.12, .7, 1., .9][row]
        for col, color in enumerate(palette):
            x, y = col * 32, row * 32
            c = tuple(min(255, int(v * shade)) for v in color)
            for a in range(32):
                for b in range(32):
                    noise = rng.choice([-5, -2, 0, 0, 0, 2, 4])
                    im.putpixel((x+a, y+b), tuple(max(0, min(255, v+noise)) for v in c)+(255,))
            dark = tuple(int(v*.55) for v in c)
            light = tuple(min(255, int(v*1.2)+8) for v in c)
            d.rectangle((x, y, x+31, y+31), outline=dark, width=2)
            d.line((x+2, y+28, x+2, y+2, x+28, y+2), fill=light, width=1)
            d.line((x+4, y+29, x+29, y+29, x+29, y+4), fill=dark, width=2)
            if col in (0, 1, 2):
                for a, b in [(5, 5), (26, 5), (5, 26), (26, 26)]:
                    d.rectangle((x+a-1, y+b-1, x+a+1, y+b+1), fill=dark)
                    d.point((x+a-1, y+b-1), fill=light)
                d.line((x+9, y+23, x+14, y+23, x+17, y+20), fill=light)
                d.line((x+20, y+8, x+23, y+8), fill=dark)
            elif col in (3, 4, 7):
                for b in range(6, 28, 5):
                    d.rectangle((x+5, y+b, x+26, y+b+2), fill=dark)
                    d.line((x+6, y+b+3, x+25, y+b+3), fill=light)
            elif col == 5:
                # Glowing RED reactor/lens tile: the chest laser comes from here.
                for a in range(11):
                    v = (255, min(200, 20+a*16), min(160, 10+a*12))
                    d.rectangle((x+4+a, y+4+a, x+27-a, y+27-a), outline=v)
                d.line((x+8, y+15, x+23, y+15), fill=(255, 235, 200), width=2)
            elif col == 6:
                for a in (8, 16, 24):
                    d.line((x+a, y+26, x+a, y+17, x+a-4, y+13, x+a-4, y+6), fill=(171, 80, 235))
                    d.rectangle((x+a-5, y+5, x+a-3, y+7), fill=(220, 141, 255))
    b = io.BytesIO()
    im.save(b, 'PNG', optimize=True)
    return b.getvalue()


def bone(name, parent=None, pivot=(0, 0, 0)):
    b = {'name': name, 'pivot': list(pivot), 'cubes': []}
    if parent:
        b['parent'] = parent
    BONES.append(b)
    return b


def cube(b, origin, size, material=0):
    # Preserve texel aspect on thin panels: no stretched square bolts/circuits.
    w, h, d = size
    uv = {}
    for i, (face, (a, bsize)) in enumerate(zip(FACES, [(w,h),(w,h),(d,h),(d,h),(w,d),(w,d)])):
        factor = min(1, 28 / max(a, bsize))
        u, v = round(a * factor, 4), round(bsize * factor, 4)
        uv[face] = {'uv': [material*32 + (32-u)/2, i*32 + (32-v)/2], 'uv_size': [u,v]}
    b['cubes'].append({'origin': list(origin), 'size': list(size), 'uv': uv})


def geometry():
    BONES.clear()
    bone('root')
    hip = bone('pelvis', 'root', (0, 64, 0))
    cube(hip, (-23, 61, -11), (46, 12, 22), 2)
    cube(hip, (-24, 65, -13), (48, 7, 4), 1)
    cube(hip, (-8, 59, -14), (16, 13, 5), 0)
    torso = bone('torso', 'root', (0, 68, 0))
    cube(torso, (-17, 71, -10), (34, 12, 20), 3)
    for y in [73, 77, 81]:
        cube(torso, (-18, y, -11), (36, 2, 2), 1)
    cube(torso, (-25, 82, -13), (50, 25, 27), 0)
    cube(torso, (-28, 96, -14), (56, 13, 29), 1)
    cube(torso, (-21, 83, -16), (42, 19, 4), 2)
    for s in [-1, 1]:
        cube(torso, (s*17-5, 85, -18), (10, 20, 4), 0)
        cube(torso, (s*18-2, 88, -19), (4, 12, 1), 6)
        cube(torso, (s*18-6, 85, 14), (12, 20, 7), 4)
        cube(torso, (s*18-4, 106, 15), (8, 5, 5), 3)
    cube(torso, (-11, 87, -19), (22, 18, 5), 1)
    cube(torso, (-8, 90, -20), (16, 12, 2), 2)
    reactor = bone('reactor', 'torso', (0, 96, -20))
    cube(reactor, (-6, 91, -21), (12, 10, 2), 5)
    cube(torso, (-6, 107, -6), (12, 7, 12), 3)
    head = bone('head', 'torso', (0, 112, 0))
    cube(head, (-13, 108, -10), (26, 18, 20), 0)
    cube(head, (-10, 126, -8), (20, 2, 17), 1)  # Exactly 128 units = 8 blocks.
    cube(head, (-14, 121, -11), (28, 4, 21), 1)
    cube(head, (-12, 112, -11), (24, 9, 2), 2)
    cube(head, (-10, 108, -12), (20, 5, 3), 4)
    cube(head, (-2, 113, -13), (4, 8, 3), 0)
    for side, x in [('left', 6), ('right', -6)]:
        cube(head, (x-4, 114, -12), (8, 6, 2), 1)
        eyes = bone('eye_'+side, 'head', (x, 117, -13))
        cube(eyes, (x-3, 115, -13), (6, 4, 1), 5)
        cube(head, (13 if x > 0 else -16, 113, -4), (3, 8, 9), 3)
    for side, s in [('left', 1), ('right', -1)]:
        x = 16*s
        thigh = bone('leg_'+side, 'root', (x, 64, 0))
        cube(thigh, (x-9, 37, -9), (18, 27, 19), 0)
        cube(thigh, (x-10, 43, -11), (20, 19, 4), 1)
        cube(thigh, (x-4, 46, -12), (8, 11, 1), 6)
        shin = bone('shin_'+side, 'leg_'+side, (x, 36, 0))
        cube(shin, (x-9, 30, -9), (18, 10, 18), 3)
        cube(shin, (x-11, 30, -13), (22, 11, 5), 2)
        cube(shin, (x-8, 32, -15), (16, 7, 3), 1)
        cube(shin, (x-10, 10, -10), (20, 22, 20), 0)
        cube(shin, (x-7, 13, -12), (14, 15, 3), 1)
        cube(shin, (x-3, 15, -13), (6, 10, 1), 6)
        for dx in [-11, 9]:
            cube(shin, (x+dx, 13, 6), (2, 18, 4), 3)
        foot = bone('foot_'+side, 'shin_'+side, (x, 10, 0))
        cube(foot, (x-12, 0, -20), (24, 5, 28), 7)
        cube(foot, (x-11, 5, -19), (22, 6, 26), 0)
        for dx in [-7, 0, 7]:
            cube(foot, (x+dx-3, 5, -21), (6, 4, 5), 1)
        ax = s*34
        arm = bone('arm_'+side, 'torso', (ax, 101, 0))
        cube(arm, (ax-9, 90, -12), (18, 17, 25), 2)
        cube(arm, (ax-12, 98, -14), (24, 11, 29), 0)
        cube(arm, (ax-10, 108, -12), (20, 2, 25), 1)
        cube(arm, (ax-7, 74, -8), (14, 18, 17), 0)
        cube(arm, (ax-4, 76, -10), (8, 12, 3), 6)
        forearm = bone('forearm_'+side, 'arm_'+side, (ax, 74, 0))
        cube(forearm, (ax-8, 69, -9), (16, 10, 18), 3)
        cube(forearm, (ax-10, 53, -11), (20, 19, 22), 0)
        cube(forearm, (ax-8, 55, -13), (16, 13, 3), 1)
        cube(forearm, (ax-5, 58, -14), (10, 6, 1), 4)
        hand = bone('hand_'+side, 'forearm_'+side, (ax, 53, 0))
        cube(hand, (ax-9, 43, -10), (18, 11, 19), 2)
        for dx in [-6, 0, 6]:
            cube(hand, (ax+dx-2.5, 40, -12), (5, 9, 7), 0)
            cube(hand, (ax+dx-2, 46, -13), (4, 3, 2), 1)
    return {'format_version': '1.12.0', 'minecraft:geometry': [{
        'description': {'identifier': 'geometry.gc.robot_colossus', 'texture_width': 256,
                        'texture_height': 256, 'visible_bounds_width': 12,
                        'visible_bounds_height': 12, 'visible_bounds_offset': [0, 5, 0]},
        'bones': BONES,
    }]}


def animations():
    anim = {}
    def add(name, duration, bones, loop=False, combat=False):
        value = {'loop': loop, 'animation_length': duration, 'bones': bones}
        if combat:
            value['anim_time_update'] = "query.property('gc:attack_tick') / 20.0"
        anim['animation.gc.colossus.'+name] = value
    add('idle', 4, {
        'reactor': {'scale': ["1 + math.sin(query.anim_time * 90) * 0.035", 1, 1]},
        'forearm_left': {'rotation': ["math.sin(query.anim_time * 90) * 1.5", 0, 0]},
        'forearm_right': {'rotation': ["-math.sin(query.anim_time * 90) * 1.5", 0, 0]},
    }, True)
    # Two-bone IK baked into ordinary editable Blockbench keyframes. The support
    # foot travels backwards at constant speed; the returning foot clears the floor.
    walking = {'root': {'position': [0, -2, 0]}}
    for side, offset in [('left', 0), ('right', .5)]:
        channels = {name: {} for name in ['leg', 'shin', 'foot', 'arm', 'forearm']}
        for i in range(33):
            time = i / 32
            phase = (time + offset) % 1
            z = -10 + 40*phase if phase < .5 else 10 - 40*(phase-.5)
            lift = 0 if phase < .5 else 7 * math.sin((phase-.5)*2*math.pi)**2
            down = 52 - lift
            distance = math.hypot(z, down)
            knee = math.acos(max(-1, min(1, (distance**2-28**2-26**2)/(2*28*26))))
            hip = math.atan2(z, down) - math.atan2(26*math.sin(knee),28+26*math.cos(knee))
            angles = [math.degrees(hip), math.degrees(knee), -math.degrees(hip+knee),
                      -z*.7, -4-2*math.sin(phase*2*math.pi)]
            for name, angle in zip(channels, angles):
                channels[name][str(time)] = [round(angle, 5), 0, 0]
        for name, keys in channels.items():
            walking[name+'_'+side] = {'rotation': keys}
    add('walk', 1, walking, True)
    # One cycle spans 2.5 blocks: 20 model units of planted stride per half-cycle.
    # The client integrates actual horizontal displacement and wraps every stride.
    # Do not depend on vanilla runtime-specific modified movement counters.
    anim['animation.gc.colossus.walk']['anim_time_update'] = 'variable.gc_walk_phase'
    add('air', 1, {
        'leg_left': {'rotation': [-12, 0, 0]}, 'leg_right': {'rotation': [-12, 0, 0]},
        'shin_left': {'rotation': [24, 0, 0]}, 'shin_right': {'rotation': [24, 0, 0]},
        'foot_left': {'rotation': [-12, 0, 0]}, 'foot_right': {'rotation': [-12, 0, 0]},
        'arm_left': {'rotation': [0, 0, -8]}, 'arm_right': {'rotation': [0, 0, 8]},
    }, True)
    add('hurt', 1, {
        'torso': {'rotation': ['-math.sin(variable.gc_hurt_remaining * 360) * 3', 0, 0]},
    }, True)
    add('aim', 2, {
        'root': {'rotation': [0, "math.min_angle(query.property('gc:aim_yaw') - query.body_y_rotation)", 0]},
        'head': {'rotation': ["query.property('gc:aim_pitch')", 0, 0]},
    }, True)
    add('laser', 2, {
        'arm_left': {'rotation': {'0.0': [0,0,0], '0.6': [-12,0,-8], '1.0': [-12,0,-8], '1.15': [4,0,-4], '2.0': [0,0,0]}},
        'arm_right': {'rotation': {'0.0': [0,0,0], '0.6': [-12,0,8], '1.0': [-12,0,8], '1.15': [4,0,4], '2.0': [0,0,0]}},
        # Chest reactor charges for one second, then the red laser leaves it.
        'reactor': {'scale': {'0.0': [1,1,1], '0.5': [1.2,1.2,1.5], '0.9': [1.45,1.45,2], '1.0': [1.6,1.6,2.4], '1.3': [1,1,1]}},
        'torso': {'rotation': {'0.0': [0,0,0], '0.9': [-6,0,0], '1.0': [-7,0,0], '1.1': [3,0,0], '1.5': [0,0,0]}},
        'eye_left': {'scale': {'0.0': [1,1,1], '0.9': [1.1,1.15,1], '1.0': [1.2,1.25,1], '1.25': [1,1,1]}},
        'eye_right': {'scale': {'0.0': [1,1,1], '0.9': [1.1,1.15,1], '1.0': [1.2,1.25,1], '1.25': [1,1,1]}},
    }, combat=True)
    add('stomp', 1.6, {
        'leg_right': {'rotation': {'0.0':[0,0,0], '0.45':[-52,0,0], '0.65':[-55,0,0], '0.8':[0,0,0], '1.6':[0,0,0]}},
        'shin_right': {'rotation': {'0.0':[0,0,0], '0.45':[62,0,0], '0.65':[62,0,0], '0.8':[0,0,0]}},
        'foot_right': {'rotation': {'0.0':[0,0,0], '0.45':[-10,0,0], '0.65':[-7,0,0], '0.8':[0,0,0]}},
        'torso': {'rotation': {'0.0':[0,0,0], '0.55':[0,0,-5], '0.8':[6,0,0], '1.1':[0,0,0]}},
        'arm_left': {'rotation': {'0.0':[0,0,0], '0.5':[-22,0,-10], '0.8':[8,0,-5], '1.6':[0,0,0]}},
        'arm_right': {'rotation': {'0.0':[0,0,0], '0.5':[20,0,12], '0.8':[-12,0,4], '1.6':[0,0,0]}},
    }, combat=True)
    return {'format_version': '1.8.0', 'animations': anim}


def behavior():
    target_filter = {'all_of': [
        {'any_of': [
            {'all_of': [
                {'test':'is_family','subject':'other','value':'player'},
                {'test':'is_game_mode','subject':'other','operator':'!=','value':'creative'},
                {'test':'is_game_mode','subject':'other','operator':'!=','value':'spectator'},
            ]},
            *[{'test':'is_family','subject':'other','value':f} for f in ['monster','goblin_caravan','goblin','goblin_giant','goblin_archer']],
        ]},
        {'test':'is_family','subject':'other','operator':'!=','value':'robot_colossus'},
    ]}
    mobile = {'minecraft:movement': {'value':0.22},
              'minecraft:behavior.melee_box_attack': {'priority':2,'speed_multiplier':1.1,'track_target':True,
                  'reach_multiplier':1.2,'cooldown_time':1.5},
              'minecraft:behavior.move_towards_target': {'priority':3,'speed_multiplier':1,'within_radius':3},
              'minecraft:behavior.random_stroll': {'priority':6,'speed_multiplier':0.65,'interval':120},
              'minecraft:behavior.look_at_player': {'priority':7,'look_distance':12},
              'minecraft:behavior.random_look_around': {'priority':8}}
    return {'format_version':'1.21.90', 'minecraft:entity': {
        'description': {'identifier':'gc:robot_colossus','is_spawnable':True,'is_summonable':True,'is_experimental':False,
            'properties': {
                'gc:action': {'type':'enum','values':['idle','laser','stomp'],'default':'idle','client_sync':True},
                'gc:attack_tick': {'type':'int','range':[0,40],'default':0,'client_sync':True},
                'gc:aim_yaw': {'type':'float','range':[-180,180],'default':0,'client_sync':True},
                'gc:aim_pitch': {'type':'float','range':[-70,75],'default':0,'client_sync':True},
            }},
        'component_groups': {'gc:mobile': mobile, 'gc:frozen': {'minecraft:movement': {'value':0}}},
        'components': {
            'minecraft:type_family': {'family':['robot_colossus','monster','mob']},
            'minecraft:health': {'value':600,'max':600},
            'minecraft:collision_box': {'width':3.2,'height':8},
            'minecraft:knockback_resistance': {'value':1},
            'minecraft:fire_immune': {}, 'minecraft:physics': {}, 'minecraft:persistent': {},
            'minecraft:pushable': {'is_pushable':False,'is_pushable_by_piston':False},
            'minecraft:movement.basic': {'max_turn':15}, 'minecraft:jump.static': {},
            'minecraft:can_climb': {}, 'minecraft:nameable': {},
            'minecraft:navigation.walk': {'avoid_water':True,'avoid_damage_blocks':True,'can_path_over_water':False,'can_pass_doors':False,'can_open_doors':False},
            'minecraft:follow_range': {'value':32},
            # Native fallback: even without scripts it punches players, monsters and goblins.
            'minecraft:attack': {'damage':20},
            'minecraft:behavior.hurt_by_target': {'priority':1,
                'entity_types':[{'filters':{'test':'is_family','subject':'other','operator':'!=','value':'robot_colossus'}}]},
            'minecraft:behavior.float': {'priority':0},
            'minecraft:behavior.nearest_attackable_target': {'priority':2,'within_radius':28,'must_see':False,
                'reselect_targets':False,'entity_types':[{'filters':target_filter,'max_dist':28}]},
            'minecraft:loot': {'table':'loot_tables/entities/robot_colossus.json'},
        },
        'events': {
            'minecraft:entity_spawned': {'add':{'component_groups':['gc:mobile']}},
            'gc:colossus_freeze': {'remove':{'component_groups':['gc:mobile']},'add':{'component_groups':['gc:frozen']}},
            'gc:colossus_resume': {'remove':{'component_groups':['gc:frozen']},'add':{'component_groups':['gc:mobile']}},
        },
    }}


def client_animation_scripts():
    """Client-only signals: basic animation must not require the combat script.

    Position deltas work for custom entities without a vanilla runtime identifier.
    Ignore teleport/first-frame jumps, retain a bounded phase, and detect damage
    from health changes instead of query.hurt_time (unreliable on the RP side).
    """
    return {
        'initialize': [
            'variable.gc_previous_x = query.position(0);',
            'variable.gc_previous_z = query.position(2);',
            'variable.gc_previous_health = query.health;',
            'variable.gc_walk_phase = 0;',
            'variable.gc_speed = 0;',
            'variable.gc_hurt_remaining = 0;',
        ],
        # Keep temp.* in ONE Molang expression: temporaries are expression-scoped.
        'pre_animation': [' '.join([
            "variable.gc_action = query.has_property('gc:action') ? query.property('gc:action') : 'idle';",
            "variable.gc_combat = variable.gc_action == 'laser' || variable.gc_action == 'stomp';",
            'temp.gc_dx = query.position(0) - variable.gc_previous_x;',
            'temp.gc_dz = query.position(2) - variable.gc_previous_z;',
            'temp.gc_distance = math.sqrt(temp.gc_dx * temp.gc_dx + temp.gc_dz * temp.gc_dz);',
            'temp.gc_step = query.delta_time > 0 && temp.gc_distance < 4 ? temp.gc_distance : 0;',
            'variable.gc_speed = math.lerp(variable.gc_speed, temp.gc_step / math.max(query.delta_time, 0.0001), math.min(1, query.delta_time * 12));',
            'temp.gc_stride = query.is_on_ground && !variable.gc_combat ? temp.gc_step / 2.5 : 0;',
            'variable.gc_walk_phase = math.mod(variable.gc_walk_phase + temp.gc_stride, 1);',
            'variable.gc_previous_x = query.position(0);',
            'variable.gc_previous_z = query.position(2);',
            'variable.gc_hurt_remaining = query.health < variable.gc_previous_health ? 0.5 : math.max(0, variable.gc_hurt_remaining - query.delta_time);',
            'variable.gc_previous_health = query.health;',
        ])],
        'animate': [
            # Always-on idle also provides a visible check that the RP is loaded.
            'idle', 'locomotion',
            {'hurt': 'variable.gc_hurt_remaining > 0 && !variable.gc_combat'},
            {'aim': 'variable.gc_combat'}, 'combat',
        ],
    }


def client():
    aliases = {k:'animation.gc.colossus.'+k for k in ['idle','walk','air','hurt','aim','laser','stomp']}
    aliases['combat'] = 'controller.animation.gc.colossus'
    aliases['locomotion'] = 'controller.animation.gc.colossus.locomotion'
    return {'format_version':'1.10.0','minecraft:client_entity': {'description': {
        'identifier':'gc:robot_colossus', 'min_engine_version':'1.21.90',
        'materials': {'default':'entity_alphatest','glow':'entity_emissive_alpha'},
        'textures': {'default':'textures/entity/robot_colossus'},
        'geometry': {'default':'geometry.gc.robot_colossus'}, 'animations': aliases,
        'scripts': client_animation_scripts(),
        'render_controllers':['controller.render.gc.colossus'],
        'spawn_egg': {'base_color':'#6027A2','overlay_color':'#CB7AFF'},
    }}}


def controller():
    states = {'idle': {'transitions': [{k: "variable.gc_action == '"+k+"'"} for k in ['laser','stomp']]}}
    for action in ['laser','stomp']:
        states[action] = {'animations':[action], 'transitions':[{'idle':"variable.gc_action != '"+action+"'"}], 'blend_transition':0.15}
    fighting = 'variable.gc_combat'
    walking = 'query.is_on_ground && variable.gc_speed > 0.05'
    locomotion = {
        'idle': {'transitions':[{'combat':fighting},{'air':'!query.is_on_ground'},{'walk':walking}], 'blend_transition':0.2},
        'walk': {'animations':['walk'], 'transitions':[{'combat':fighting},{'air':'!query.is_on_ground'},{'idle':'variable.gc_speed < 0.02'}], 'blend_transition':0.2},
        'air': {'animations':['air'], 'transitions':[{'combat':fighting},{'walk':walking},{'idle':'query.is_on_ground'}], 'blend_transition':0.2},
        'combat': {'transitions':[{'idle':'!variable.gc_combat'}], 'blend_transition':0.15},
    }
    return {'format_version':'1.17.30','animation_controllers': {
        'controller.animation.gc.colossus': {'initial_state':'idle','states':states},
        'controller.animation.gc.colossus.locomotion': {'initial_state':'idle','states':locomotion}}}


def particle(name, spark=False):
    return {'format_version':'1.10.0','particle_effect': {
        'description': {'identifier':'gc:colossus_'+name,'basic_render_parameters':{
            'material':'particles_add','texture':'textures/particle/colossus_glow'}},
        'components': {
            'minecraft:emitter_rate_instant': {'num_particles':1},
            'minecraft:emitter_lifetime_once': {'active_time':0.01},
            'minecraft:emitter_shape_point': {'offset':[0,0,0],'direction':[0,1,0]},
            'minecraft:particle_lifetime_expression': {'max_lifetime':0.4 if spark else 0.24},
            'minecraft:particle_initial_speed':0.4 if spark else 0,
            'minecraft:particle_motion_dynamic': {'linear_acceleration':[0,0,0]},
            'minecraft:particle_appearance_billboard': {'size':[0.3 if spark else 0.22]*2,
                'facing_camera_mode':'rotate_xyz','uv': {'texture_width':16,'texture_height':16,'uv':[0,0],'uv_size':[16,16]}},
            'minecraft:particle_appearance_tinting': {'color':[1,0.45,0.1,1] if spark else [1,0.06,0.03,1]},
        }}}


def blockbench(geo, anim, png):
    groups, elements = {}, []
    for b in geo['minecraft:geometry'][0]['bones']:
        # Bedrock <-> Blockbench convention: reflect X; rotations reflect X and Y.
        pivot = [-b['pivot'][0], b['pivot'][1], b['pivot'][2]]
        group = {'name':b['name'],'origin':pivot,'rotation':[0,0,0],'uuid':uid('bone/'+b['name']),
                 'export':True,'isOpen':True,'visibility':True,'children':[]}
        groups[b['name']] = group
        for i, c in enumerate(b['cubes']):
            x,y,z = c['origin']; w,h,d = c['size']
            faces = {}
            for face in FACES:
                # Blockbench's Bedrock codec keeps face names even when reflecting X.
                source = c['uv'][face]
                u,v = source['uv']; du,dv = source['uv_size']
                faces[face] = {'uv':[u+du,v+dv,u,v] if face in ['up','down'] else [u,v,u+du,v+dv], 'texture':0}
            e = {'name':b['name']+'_'+str(i), 'type':'cube','uuid':uid(b['name']+'/'+str(i)),
                 'from':[-x-w,y,z],'to':[-x,y+h,z+d], 'origin':pivot,'rotation':[0,0,0],
                 'box_uv':False,'rescale':False,'locked':False,'render_order':'default','visibility':True,
                 'autouv':0,'color':5,'faces':faces}
            elements.append(e); group['children'].append(e['uuid'])
    outliner = []
    for b in BONES:
        if 'parent' in b: groups[b['parent']]['children'].append(groups[b['name']])
        else: outliner.append(groups[b['name']])
    animations_bb = []
    for name,a in anim['animations'].items():
        aa = {'uuid':uid(name),'name':name,'loop':'loop' if a['loop'] else 'once',
              'override':False,'length':a['animation_length'],'snapping':20,'animators':{}}
        for b,channels in a['bones'].items():
            keys = []
            for channel,data in channels.items():
                frames = data if isinstance(data,dict) else {'0.0':data}
                for time,vector in frames.items():
                    v = list(vector)
                    for i in range(3):
                        if (channel=='rotation' and i in (0,1)) or (channel=='position' and i==0):
                            v[i] = -v[i] if isinstance(v[i],(float,int)) else '-('+v[i]+')'
                    keys.append({'uuid':uid(name+b+channel+time),'channel':channel,'time':float(time),'color':-1,
                                 'interpolation':'linear','data_points':[dict(zip(['x','y','z'],map(str,v)))]})
            aa['animators'][uid('bone/'+b)] = {'name':b,'type':'bone','keyframes':keys}
        animations_bb.append(aa)
    return {'meta':{'format_version':'4.10','model_format':'bedrock','box_uv':False},
        'name':'Colosso Robot / Violet Siege Unit','model_identifier':'gc.robot_colossus',
        'visible_box':[12,12,5],'variable_placeholders':"query.property('gc:aim_pitch') = 0;\nquery.property('gc:aim_yaw') = 0;\nquery.body_y_rotation = 0;\nvariable.gc_hurt_remaining = 0.25;",
        'resolution':{'width':256,'height':256},'elements':elements,'outliner':outliner,
        'textures':[{'path':'textures/robot_colossus.png','relative_path':'textures/robot_colossus.png',
                     'name':'robot_colossus.png','folder':'','namespace':'','id':'0','particle':False,
                     'render_mode':'default','render_sides':'auto','frame_time':1,'visible':True,'internal':True,
                     'saved':True,'uuid':uid('atlas'),'source':'data:image/png;base64,'+base64.b64encode(png).decode()}],
        'animations':animations_bb}


def build():
    path = ROOT/'Goblin-Caravan-Blockbench.zip'
    with zipfile.ZipFile(path) as z:
        entries = {n:z.read(n) for n in z.namelist()}
    geo, anim, png = geometry(), animations(), texture()
    generated = {
        BP+'entities/robot_colossus.json':behavior(),
        BP+'loot_tables/entities/robot_colossus.json':{'pools':[{'rolls':1,'entries':[{'type':'item','name':'minecraft:amethyst_shard','weight':1,'functions':[{'function':'set_count','count':{'min':4,'max':8}}]}]}]},
        RP+'entity/robot_colossus.entity.json':client(),
        RP+'models/entity/robot_colossus.geo.json':geo,
        RP+'animations/colossus.animation.json':anim,
        RP+'animation_controllers/colossus.json':controller(),
        RP+'render_controllers/colossus.render_controllers.json':{'format_version':'1.8.0','render_controllers':{
            'controller.render.gc.colossus':{'geometry':'Geometry.default','materials':[{'*':'Material.default'},{'eye_*':'Material.glow'},{'reactor':'Material.glow'}],'textures':['Texture.default']}}},
        RP+'particles/colossus_laser.json':particle('laser'),
        RP+'particles/colossus_spark.json':particle('spark', True),
        'geometry/robot_colossus.geo.json':geo,
        'animations/colossus.animation.json':anim,
        'robot_colossus.bbmodel':blockbench(geo, anim, png),
    }
    entries.update({n:encoded(v) for n,v in generated.items()})
    entries[RP+'textures/entity/robot_colossus.png'] = png
    entries['textures/robot_colossus.png'] = png
    glow = Image.new('RGBA',(16,16),(0,0,0,0))
    for y in range(16):
        for x in range(16):
            r = ((x-7.5)**2+(y-7.5)**2)**.5/7.5
            if r < 1: glow.putpixel((x,y),(255,255,255,int(255*(1-r)**0.7)))
    buffer = io.BytesIO(); glow.save(buffer,'PNG')
    entries[RP+'textures/particle/colossus_glow.png'] = buffer.getvalue()
    entries[BP+'scripts/colossus.js'] = (ROOT/'minecraft/colossus.js').read_bytes()
    script = entries[BP+'scripts/main.js'].decode()
    if "import './colossus.js';" not in script:
        script = "import './colossus.js';\n" + script
    entries[BP+'scripts/main.js'] = script.encode()
    for prefix in [BP,RP]:
        manifest = json.loads(entries[prefix+'manifest.json'])
        manifest['header']['version'] = VERSION
        manifest['header']['description'] = 'Goblin Caravan 1.2.3 — Colosso Robot viola, laser rosso dal petto e pestata'
        for m in manifest['modules']: m['version'] = VERSION
        for dep in manifest.get('dependencies',[]):
            if 'uuid' in dep: dep['version'] = VERSION
        entries[prefix+'manifest.json'] = encoded(manifest)
    for language,name in [('it_IT','Colosso Robot'),('en_US','Robot Colossus')]:
        p = RP+'texts/'+language+'.lang'
        text = '\n'.join(l for l in entries[p].decode().splitlines() if 'gc:robot_colossus' not in l)+'\n'
        entries[p] = (text+f'entity.gc:robot_colossus.name={name}\nitem.spawn_egg.entity.gc:robot_colossus.name={name}\n').encode()
    notes = entries['LEGGIMI.txt'].decode().split('\nCOLOSSO ROBOT — ')[0]
    for previous in ['1.1.0', '1.2.0', '1.2.1', '1.2.2']:
        notes = notes.replace('GOBLIN CARAVAN — '+previous, 'GOBLIN CARAVAN — 1.2.3')
    notes += '''\nCOLOSSO ROBOT — 1.2.3
NOVITÀ 1.2.3 — LASER ROSSO DAL PETTO
Il colosso ora ATTACCA davvero mostri, goblin (gigante e arciere) e player in
Sopravvivenza/Avventura. Il laser è ROSSO, parte dal reattore sul petto (non più
dagli occhi), dà fuoco al bersaglio per 10 secondi e infligge 200 danni: uccide
player, zombie e goblin con un colpo (resta solo il Totem dell'immortalità).
Dove il raggio colpisce accende un fuoco sul terreno. Scie di fiamme lungo il raggio.
Correzioni: la vista partiva da 7 blocchi d'altezza e sotto alberi/soffitti vedeva
un muro a 0 blocchi, quindi non trovava mai bersagli. Ora mira dal petto e ignora
il blocco appena attaccato al corpo. Goblin di altri addon riconosciuti anche dal
nome ("goblin" nell'ID). Attacco corpo a corpo nativo (20 danni) come riserva se
gli script non partono, e contrattacco verso chi lo colpisce.
ATTENZIONE: il fuoco può propagarsi (gamerule doFireTick) — prova lontano da legno.
''' + '''\nSTORICO 1.2.2
Nuovo mob gc:robot_colossus; nessuno spawn naturale. Uovo in Creativa oppure:
/summon gc:robot_colossus ~ ~ ~
Altezza a riposo esatta: 8 blocchi (128 unità modello), collisione 3,2 × 8.
Armatura originale tutta in tonalità viola, atlas pixel art 256×256 con piastre,
bulloni, circuiti, ventole, pistoni, dita, battistrada, reattore e lenti oculari.
600 punti vita, resistente al contraccolpo e immune al fuoco. Drop: 4–8 ametiste.
Attacca player in Sopravvivenza/Avventura, famiglia monster, goblin_caravan e goblin.
Esclude altri colossi, Creativa/Spettatore e animali passivi. Goblin di addon esterni
sono riconosciuti se dichiarano una di queste famiglie, non dal solo nome.
Laser: raggio 28 blocchi, carica visibile 1 secondo, un raggio ROSSO dal petto,
200 danni + fuoco per 10 s a ogni vittima colpita, cooldown 3,5 s.
Si ferma ai blocchi solidi e al primo corpo vivo; non danneggia i passivi.
La mira si blocca 0,2 s prima dello sparo: si può schivare. Danni una sola volta.
Pestata: solleva la gamba destra, impatto a 0,8 s, 24 danni base in raggio 4 dal
piede, respinta, anelli viola e suono; cooldown 2,7 s. Pareti bloccano il danno.
Richiede suolo, differenza verticale massima 2,5 blocchi; non colpisce volanti alti.
Laser e pestata hanno recupero; non distruggono blocchi. Il laser accende fuoco.
Animazioni: idle/reattore, camminata IK, caduta, danno, mira, laser e pestata.
1.2.2: idle sempre attivo sul client, anche senza script di combattimento.
Camminata basata sullo spostamento X/Z reale, non sui contatori modified_move_speed
/ modified_distance_moved: fase limitata a un ciclo, niente salti dopo teletrasporti
lunghi, pausa in aria e durante gli attacchi. Non serve un runtime_identifier vanilla.
Danno rilevato dal calo di salute: non dipende da query.hurt_time nel Resource Pack.
Proprietà gc:action non ancora sincronizzata: fallback idle, non posa di combattimento.
Piedi livellati, transizioni morbide e mira senza giri a 360°.
Corretto il blocco del combattimento quando lo script parte su un tick dispari.
La rotazione iniziale precede la carica: niente scatti istantanei di 180°.
UV proporzionate per ridurre lo stiramento delle piastre strette.
L'istante di impatto segue la proprietà sincronizzata gc:attack_tick (20 tick/s).
Lo script recupera gli attacchi interrotti al ricaricamento e pulisce i mob scaricati.

BLOCKBENCH — COLOSSO
Apri robot_colossus.bbmodel: gerarchia, UV, texture incorporata e sette animazioni
editabili incluse. File costruito programmaticamente nel formato Blockbench;
non è stato eseguito l'editor grafico qui. Il modello non usa plugin GeckoLib.
Alternative: geometry/robot_colossus.geo.json, textures/robot_colossus.png e
animations/colossus.animation.json. Gli stessi asset sono nel resource pack.
Sorgenti dell'addon completo: addon-source/. Il repository contiene il generatore
minecraft/build_colossus.py (Python + Pillow) e minecraft/colossus.js.

COLLAUDO COLOSSO
Controlli automatici su pacchetti, UV, altezza, animazioni, proprietà e combattimento
con API simulate. NON collaudato dentro Minecraft/Blockbench: verifica Content Log,
importazione su Bedrock 1.21.90+, orientamento laser a tutte le rotazioni, pestata,
pareti, salvataggio/ricaricamento e più colossi. Il multiplayer può mostrare ritardo
visivo di rete; le collisioni sono server-side. Suoni vanilla, particelle originali.
INSTALLAZIONE AGGIORNAMENTO
Importa Goblin-Caravan.mcaddon 1.2.3 e attiva ENTRAMBI i pacchetti BP e RP
nel mondo. Esci e riapri il mondo dopo avere aggiornato; gli UUID sono invariati
per sostituire la vecchia versione. Non servono esperimenti o Beta APIs.
In Creativa il colosso NON attacca il giocatore: genera uno zombie per provarlo.
Se mancano animazioni controlla che il Resource Pack 1.2.3 sia attivo; se non
attacca controlla Behavior Pack, Content Log e versione Bedrock 1.21.90+.
Per provare usa una zona aperta (almeno 12×12 e 10 blocchi di altezza) e difficoltà
Normale; genera zombie e goblin, poi passa in Sopravvivenza. Backup del mondo.
Controlla idle (reattore e avambracci), camminata per più di 10 blocchi, arresto,
caduta, danno, laser a distanza, pestata da vicino, poi salvataggio/ricaricamento.
Per isolare caricamento RP da condizioni/controller, con trucchi abilitati:
/playanimation @e[type=gc:robot_colossus,c=1] animation.gc.colossus.stomp
Se neppure questo muove la gamba, verifica RP 1.2.3, pacchetti duplicati/priorità
ed errori nel Content Log. Se il comando funziona ma il combattimento no, verifica
BP 1.2.3 e gli errori script. Nessun blocco specifico riprodotto nel motore grafico:
questo aggiornamento è verificato con test automatici, non dentro Minecraft.
'''
    entries['LEGGIMI.txt'] = entries['addon-source/LEGGIMI.txt'] = notes.encode()
    # Assemble both packs from EXACTLY the bytes exposed in addon-source/.
    addon = {name:archive({n[len(prefix):]:v for n,v in entries.items() if n.startswith(prefix)})
             for prefix,name in [(BP,'Goblin_Caravan_BP.mcpack'),(RP,'Goblin_Caravan_RP.mcpack')]}
    addon['LEGGIMI.txt'] = notes.encode()
    path.write_bytes(archive(entries))
    (ROOT/'Goblin-Caravan.mcaddon').write_bytes(archive(addon))
    print(f'Built 1.2.3: {len(BONES)} bones, {sum(len(b["cubes"]) for b in BONES)} cubes, 7 animations, 256px atlas')


if __name__ == '__main__':
    build()
