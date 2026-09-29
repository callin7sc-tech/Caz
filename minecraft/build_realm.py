#!/usr/bin/env python3
"""Goblin Caravan 1.3.0 builder: removes the robot colossus and adds the Goblin Realm.

Run from any directory: python minecraft/build_realm.py (requires Pillow).
Reads the existing Goblin-Caravan-Blockbench.zip (unchanged goblin assets), drops
every robot-colossus file, adds the moss-brick portal, the realm blocks/trees,
recipes, loot, textures and scripts, then rewrites BOTH archives. Deterministic.
"""
import io
import json
import random
import zipfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BP = 'addon-source/Goblin_Caravan_BP/'
RP = 'addon-source/Goblin_Caravan_RP/'
VERSION = [1, 3, 0]
ENGINE = [1, 26, 30]            # stable DimensionRegistry: Bedrock 26.30 / @minecraft/server 2.8.0
SCRIPT_API = '2.8.0'
BLOCK_FORMAT = '1.21.90'
TEX = 'textures/blocks/gc/'


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def archive(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, value in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, value)
    return buf.getvalue()


def png(image):
    b = io.BytesIO()
    image.save(b, 'PNG', optimize=True)
    return b.getvalue()


# ------------------------------------------------------------------ textures
def clamp(c):
    return tuple(max(0, min(255, int(v))) for v in c)


def shade(c, f):
    return clamp(v * f for v in c)


def noisy(rng, base, spread=14, size=16, alpha=255):
    im = Image.new('RGBA', (size, size))
    for x in range(size):
        for y in range(size):
            n = rng.randint(-spread, spread)
            im.putpixel((x, y), clamp(v + n for v in base) + (alpha,))
    return im


def speckle(im, rng, colors, amount):
    for _ in range(amount):
        x, y = rng.randrange(im.width), rng.randrange(im.height)
        im.putpixel((x, y), clamp(rng.choice(colors)) + (255,))
    return im


def moss_bricks(rng):
    im = noisy(rng, (70, 110, 45), 10)
    mortar = (40, 58, 30)
    for y in range(16):
        for x in range(16):
            row = y // 4
            off = 0 if row % 2 == 0 else 4
            if y % 4 == 3 or (x + off) % 8 == 7:
                im.putpixel((x, y), mortar + (255,))
            elif y % 4 == 0:
                im.putpixel((x, y), shade(im.getpixel((x, y))[:3], 1.18) + (255,))
    return speckle(im, rng, [(120, 170, 70), (95, 140, 55), (150, 190, 90)], 14)


def portal_strip(rng, frames=8):
    strip = Image.new('RGBA', (16, 16 * frames))
    for f in range(frames):
        for x in range(16):
            for y in range(16):
                import math
                v = math.sin((x * 0.9 + y * 0.6) + f * 0.8) + math.sin((x * 0.4 - y * 1.1) - f * 0.6)
                t = (v + 2) / 4
                c = (int(30 + 60 * t), int(150 + 90 * t), int(40 + 50 * t))
                if rng.random() < 0.04:
                    c = (200, 255, 150)
                strip.putpixel((x, f * 16 + y), clamp(c) + (int(170 + 60 * t),))
    return strip


def grass_top(rng):
    im = noisy(rng, (84, 150, 48), 16)
    return speckle(im, rng, [(120, 190, 70), (60, 110, 35), (170, 210, 90)], 20)


def soil(rng):
    im = noisy(rng, (86, 62, 44), 12)
    return speckle(im, rng, [(60, 42, 30), (110, 82, 58), (70, 90, 45)], 18)


def grass_side(rng):
    im = soil(rng)
    for x in range(16):
        depth = 3 + rng.randint(0, 2)
        for y in range(depth):
            im.putpixel((x, y), clamp((84 + rng.randint(-14, 14), 150 + rng.randint(-14, 14), 48)) + (255,))
    return im


def stone(rng):
    im = noisy(rng, (78, 92, 80), 9)
    for _ in range(5):
        x, y = rng.randrange(16), rng.randrange(16)
        for i in range(rng.randint(2, 5)):
            if 0 <= x + i < 16:
                im.putpixel((x + i, y), (54, 64, 56, 255))
    return speckle(im, rng, [(100, 130, 95), (60, 72, 62)], 12)


def ore(rng):
    im = stone(rng)
    for cx, cy in [(4, 4), (11, 6), (6, 11), (12, 12)]:
        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1), (-1, 0)]:
            im.putpixel(((cx + dx) % 16, (cy + dy) % 16), (235, 190, 60, 255) if rng.random() < .7 else (255, 235, 130, 255))
    return im


def crystal(rng):
    im = noisy(rng, (40, 160, 110), 10)
    for i in range(16):
        im.putpixel((i, i), (170, 255, 210, 255))
        im.putpixel((15 - i, i), (120, 230, 180, 255))
        im.putpixel((i, 8), (90, 210, 150, 255))
    return speckle(im, rng, [(220, 255, 240)], 8)


def log_side(rng):
    im = noisy(rng, (86, 64, 40), 8)
    for x in range(16):
        if x % 4 == 0:
            for y in range(16):
                im.putpixel((x, y), (58, 42, 26, 255))
    for _ in range(26):   # moss patches creeping on the bark
        x, y = rng.randrange(16), rng.randrange(16)
        im.putpixel((x, y), clamp((80 + rng.randint(-15, 15), 140, 50)) + (255,))
    return im


def log_top(rng):
    im = noisy(rng, (150, 118, 76), 8)
    for x in range(16):
        for y in range(16):
            r = max(abs(x - 7.5), abs(y - 7.5))
            if int(r) in (2, 5):
                im.putpixel((x, y), (112, 84, 52, 255))
            if r > 7:
                im.putpixel((x, y), (80, 120, 45, 255))
    return im


def leaves(rng):
    im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    for x in range(16):
        for y in range(16):
            if rng.random() < 0.8:
                im.putpixel((x, y), clamp((60 + rng.randint(-20, 25), 130 + rng.randint(-25, 30), 40 + rng.randint(-10, 15))) + (255,))
    return speckle(im, rng, [(160, 210, 90), (40, 90, 30)], 10)


def planks(rng):
    im = noisy(rng, (120, 110, 60), 8)
    for y in range(16):
        if y % 4 == 3:
            for x in range(16):
                im.putpixel((x, y), (74, 66, 34, 255))
    for y0 in range(0, 16, 4):
        x = (y0 * 5 + 3) % 16
        for y in range(y0, y0 + 3):
            im.putpixel((x, y), (74, 66, 34, 255))
    return speckle(im, rng, [(90, 140, 60)], 6)


def glow_stem(rng):
    im = noisy(rng, (200, 196, 170), 8)
    for x in (3, 8, 12):
        for y in range(16):
            im.putpixel((x, y), (168, 160, 132, 255))
    return im


def glow_cap(rng):
    im = noisy(rng, (40, 190, 170), 14)
    for _ in range(9):
        x, y = rng.randrange(1, 15), rng.randrange(1, 15)
        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            im.putpixel((x + dx - 1, y + dy - 1), (210, 255, 150, 255))
    return im


def plant(rng, stem, head, kind):
    im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    if kind == 'sapling':
        for y in range(8, 16):
            im.putpixel((7, y), stem + (255,))
        for x in range(3, 13):
            for y in range(1, 10):
                if (x - 7.5) ** 2 / 25 + (y - 5) ** 2 / 18 < 1 and rng.random() < .85:
                    im.putpixel((x, y), clamp(v + rng.randint(-20, 20) for v in head) + (255,))
    elif kind == 'mushroom':
        for y in range(9, 16):
            for x in (7, 8):
                im.putpixel((x, y), stem + (255,))
        for x in range(3, 13):
            for y in range(4, 10):
                if (x - 7.5) ** 2 / 25 + (y - 9) ** 2 / 25 < 1:
                    im.putpixel((x, y), clamp(v + rng.randint(-15, 15) for v in head) + (255,))
        for x, y in [(5, 6), (9, 5), (10, 8), (6, 8)]:
            im.putpixel((x, y), (255, 240, 200, 255))
    else:  # fern
        for i in range(7):
            for side in (-1, 1):
                for j in range(4 - i // 2):
                    x, y = 7 + side * (j + 1), 15 - i * 2 - j // 2
                    if 0 <= y < 16:
                        im.putpixel((x, y), clamp(v + rng.randint(-20, 20) for v in head) + (255,))
            im.putpixel((7, 15 - i * 2), stem + (255,))
            im.putpixel((7, 14 - i * 2), stem + (255,))
    return im


def textures():
    rng = random.Random(30928)
    t = {
        'moss_bricks': moss_bricks(rng), 'grass_top': grass_top(rng), 'grass_side': grass_side(rng),
        'soil': soil(rng), 'stone': stone(rng), 'gold_ore': ore(rng), 'crystal': crystal(rng),
        'mossbark_log': log_side(rng), 'mossbark_log_top': log_top(rng), 'mossbark_leaves': leaves(rng),
        'mossbark_planks': planks(rng), 'glowcap_stem': glow_stem(rng), 'glowcap_cap': glow_cap(rng),
        'mossbark_sapling': plant(rng, (86, 64, 40), (70, 150, 50), 'sapling'),
        'glowcap_sprout': plant(rng, (220, 214, 190), (40, 200, 175), 'mushroom'),
        'goblin_mushroom': plant(rng, (230, 220, 190), (190, 60, 150), 'mushroom'),
        'goblin_fern': plant(rng, (60, 100, 35), (90, 170, 60), 'fern'),
        'goblin_portal': portal_strip(rng),
    }
    return {k: png(v) for k, v in t.items()}


def glow_particle():
    im = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
    for y in range(16):
        for x in range(16):
            r = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** .5 / 7.5
            if r < 1:
                im.putpixel((x, y), (255, 255, 255, int(255 * (1 - r) ** 0.7)))
    return png(im)


# -------------------------------------------------------------------- blocks
# id: (it name, en name, faces, extras)
BLOCKS = {
    'goblin_moss_bricks': ('Mattoni di muschio goblin', 'Goblin Moss Bricks', {'*': 'moss_bricks'},
                           dict(hardness=2, blast=6, sound='stone', color='#4E7A31', category='construction')),
    'goblin_grass': ('Erba goblin', 'Goblin Grass', {'*': 'grass_side', 'up': 'grass_top', 'down': 'soil'},
                     dict(hardness=0.6, blast=0.6, sound='grass', color='#549630', loot='soil', category='nature')),
    'goblin_soil': ('Terra goblin', 'Goblin Soil', {'*': 'soil'},
                    dict(hardness=0.5, blast=0.5, sound='gravel', color='#563E2C', category='nature')),
    'goblin_stone': ('Pietra goblin', 'Goblin Stone', {'*': 'stone'},
                     dict(hardness=1.5, blast=6, sound='stone', color='#4E5C50', category='nature')),
    'goblin_gold_ore': ('Minerale d\'oro goblin', 'Goblin Gold Ore', {'*': 'gold_ore'},
                        dict(hardness=3, blast=3, sound='stone', color='#EBBE3C', loot='nuggets', category='nature')),
    'goblin_crystal': ('Cristallo goblin', 'Goblin Crystal', {'*': 'crystal'},
                       dict(hardness=1.5, blast=1.5, sound='amethyst_block', color='#28A06E', light=9, loot='crystal', category='nature')),
    'mossbark_log': ('Tronco di muschiocorteccia', 'Mossbark Log', {'*': 'mossbark_log', 'up': 'mossbark_log_top', 'down': 'mossbark_log_top'},
                     dict(hardness=2, blast=2, sound='wood', color='#564028', flammable=True, category='nature')),
    'mossbark_leaves': ('Foglie di muschiocorteccia', 'Mossbark Leaves', {'*': 'mossbark_leaves'},
                        dict(hardness=0.2, blast=0.2, sound='grass', color='#3C8228', render='alpha_test', flammable=True,
                             loot='leaves', dampening=1, category='nature')),
    'mossbark_planks': ('Assi di muschiocorteccia', 'Mossbark Planks', {'*': 'mossbark_planks'},
                        dict(hardness=2, blast=3, sound='wood', color='#786E3C', flammable=True, category='construction')),
    'glowcap_stem': ('Gambo di fungoluce', 'Glowcap Stem', {'*': 'glowcap_stem'},
                     dict(hardness=0.8, blast=0.8, sound='wood', color='#C8C4AA', category='nature')),
    'glowcap_cap': ('Cappello di fungoluce', 'Glowcap Cap', {'*': 'glowcap_cap'},
                    dict(hardness=0.4, blast=0.4, sound='wood', color='#28BEAA', light=13, loot='cap', category='nature')),
}
PLANTS = {
    'mossbark_sapling': ('Germoglio di muschiocorteccia', 'Mossbark Sapling', 'gc:sapling'),
    'glowcap_sprout': ('Spora di fungoluce', 'Glowcap Sprout', 'gc:sapling'),
    'goblin_mushroom': ('Fungo goblin', 'Goblin Mushroom', None),
    'goblin_fern': ('Felce goblin', 'Goblin Fern', None),
}
SOILS = ['gc:goblin_grass', 'gc:goblin_soil', 'minecraft:grass_block', 'minecraft:dirt', 'minecraft:moss_block',
         'minecraft:podzol', 'minecraft:coarse_dirt', 'minecraft:rooted_dirt', 'minecraft:mycelium']


def material(faces, render='opaque'):
    return {face: {'texture': 'gc_' + tex, 'render_method': render} for face, tex in faces.items()}


def cube_block(ident, faces, o):
    c = {
        'minecraft:destructible_by_mining': {'seconds_to_destroy': o['hardness']},
        'minecraft:destructible_by_explosion': {'explosion_resistance': o['blast']},
        'minecraft:material_instances': material(faces, o.get('render', 'opaque')),
        'minecraft:map_color': o['color'],
    }
    if 'light' in o:
        c['minecraft:light_emission'] = o['light']
    if 'dampening' in o:
        c['minecraft:light_dampening'] = o['dampening']
    if o.get('flammable'):
        c['minecraft:flammable'] = {'catch_chance_modifier': 5, 'destroy_chance_modifier': 20}
    if 'loot' in o:
        c['minecraft:loot'] = f'loot_tables/blocks/gc_{ident}.json'
    return {'format_version': BLOCK_FORMAT, 'minecraft:block': {
        'description': {'identifier': 'gc:' + ident, 'menu_category': {'category': o['category']}},
        'components': c}}


def plant_block(ident, component):
    c = {
        'minecraft:geometry': 'geometry.gc.cross',
        'minecraft:material_instances': {'*': {'texture': 'gc_' + ident, 'render_method': 'alpha_test', 'face_dimming': False}},
        'minecraft:collision_box': False,
        'minecraft:selection_box': {'origin': [-5, 0, -5], 'size': [10, 12, 10]},
        'minecraft:destructible_by_mining': {'seconds_to_destroy': 0},
        'minecraft:destructible_by_explosion': {'explosion_resistance': 0},
        'minecraft:light_dampening': 0,
        'minecraft:flammable': {'catch_chance_modifier': 60, 'destroy_chance_modifier': 100},
        'minecraft:placement_filter': {'conditions': [{'allowed_faces': ['up'], 'block_filter': SOILS}]},
        'minecraft:map_color': '#46962F',
    }
    if ident == 'glowcap_sprout':
        c['minecraft:light_emission'] = 6
    if ident == 'goblin_mushroom':
        c['minecraft:light_emission'] = 3
    if component:
        c[component] = {}
    return {'format_version': BLOCK_FORMAT, 'minecraft:block': {
        'description': {'identifier': 'gc:' + ident, 'menu_category': {'category': 'nature'}},
        'components': c}}


def portal_block():
    return {'format_version': BLOCK_FORMAT, 'minecraft:block': {
        'description': {'identifier': 'gc:goblin_portal', 'menu_category': {'category': 'none'},
                        'states': {'gc:axis': ['x', 'z']}},
        'components': {
            'minecraft:geometry': 'geometry.gc.portal_pane',
            'minecraft:material_instances': {'*': {'texture': 'gc_goblin_portal', 'render_method': 'blend', 'face_dimming': False}},
            'minecraft:collision_box': False,
            'minecraft:selection_box': {'origin': [-8, 0, -2], 'size': [16, 16, 4]},
            'minecraft:destructible_by_mining': False,
            'minecraft:destructible_by_explosion': False,
            'minecraft:light_emission': 11,
            'minecraft:light_dampening': 0,
            'minecraft:loot': 'loot_tables/blocks/gc_empty.json',
            'minecraft:map_color': '#3CC850',
            'minecraft:tick': {'interval_range': [8, 24], 'looping': True},
            'gc:portal_fx': {},
        },
        'permutations': [{'condition': "q.block_state('gc:axis') == 'z'",
                          'components': {'minecraft:transformation': {'rotation': [0, 90, 0]}}}],
    }}


def uv_all(w, h, d):
    return {f: {'uv': [0, 0], 'uv_size': s} for f, s in
            [('north', [16, 16]), ('south', [16, 16]), ('east', [16, 16]), ('west', [16, 16]),
             ('up', [16, 16]), ('down', [16, 16])]}


def geometries():
    cross = {'format_version': '1.12.0', 'minecraft:geometry': [{
        'description': {'identifier': 'geometry.gc.cross', 'texture_width': 16, 'texture_height': 16},
        'bones': [{'name': 'plant', 'pivot': [0, 0, 0], 'cubes': [
            {'origin': [-8, 0, 0], 'size': [16, 16, 0], 'pivot': [0, 0, 0], 'rotation': [0, 45, 0],
             'uv': {'north': {'uv': [0, 0], 'uv_size': [16, 16]}, 'south': {'uv': [0, 0], 'uv_size': [16, 16]}}},
            {'origin': [-8, 0, 0], 'size': [16, 16, 0], 'pivot': [0, 0, 0], 'rotation': [0, -45, 0],
             'uv': {'north': {'uv': [0, 0], 'uv_size': [16, 16]}, 'south': {'uv': [0, 0], 'uv_size': [16, 16]}}},
        ]}]}]}
    pane = {'format_version': '1.12.0', 'minecraft:geometry': [{
        'description': {'identifier': 'geometry.gc.portal_pane', 'texture_width': 16, 'texture_height': 16},
        'bones': [{'name': 'portal', 'pivot': [0, 0, 0], 'cubes': [
            {'origin': [-8, 0, -2], 'size': [16, 16, 4], 'uv': {
                'north': {'uv': [0, 0], 'uv_size': [16, 16]}, 'south': {'uv': [0, 0], 'uv_size': [16, 16]},
                'east': {'uv': [0, 0], 'uv_size': [4, 16]}, 'west': {'uv': [0, 0], 'uv_size': [4, 16]},
                'up': {'uv': [0, 0], 'uv_size': [16, 4]}, 'down': {'uv': [0, 0], 'uv_size': [16, 4]}}}]}]}]}
    return cross, pane


def loot(entries):
    return {'pools': [{'rolls': 1, 'entries': entries}]} if entries else {'pools': []}


def item(name, lo=1, hi=1, weight=1):
    e = {'type': 'item', 'name': name, 'weight': weight}
    if (lo, hi) != (1, 1):
        e['functions'] = [{'function': 'set_count', 'count': {'min': lo, 'max': hi}}]
    return e


def loot_tables():
    return {
        'gc_empty': loot([]),
        'gc_goblin_grass': loot([item('gc:goblin_soil')]),
        'gc_goblin_gold_ore': loot([item('minecraft:gold_nugget', 2, 6)]),
        'gc_goblin_crystal': loot([item('minecraft:amethyst_shard', 1, 3), item('gc:goblin_crystal', weight=1)]),
        'gc_mossbark_leaves': {'pools': [
            {'rolls': 1, 'entries': [item('gc:mossbark_sapling'), {'type': 'empty', 'weight': 11}]},
            {'rolls': 1, 'entries': [item('minecraft:stick', 1, 2), {'type': 'empty', 'weight': 20}]}]},
        'gc_glowcap_cap': loot([item('gc:glowcap_sprout', weight=2), item('gc:glowcap_cap', weight=3),
                                {'type': 'empty', 'weight': 5}]),
    }


def recipes():
    def shaped(name, pattern, key, result, count=1):
        return {'format_version': '1.20.10', 'minecraft:recipe_shaped': {
            'description': {'identifier': 'gc:' + name}, 'tags': ['crafting_table'],
            'pattern': pattern, 'key': key, 'result': {'item': result, 'count': count}}}

    def shapeless(name, ingredients, result, count=1):
        return {'format_version': '1.20.10', 'minecraft:recipe_shapeless': {
            'description': {'identifier': 'gc:' + name}, 'tags': ['crafting_table'],
            'ingredients': ingredients, 'result': {'item': result, 'count': count}}}
    return {
        # The portal block: 9 moss blocks in a 3x3 grid.
        'goblin_moss_bricks': shaped('goblin_moss_bricks', ['###', '###', '###'],
                                     {'#': {'item': 'minecraft:moss_block'}}, 'gc:goblin_moss_bricks'),
        'mossbark_planks': shapeless('mossbark_planks', [{'item': 'gc:mossbark_log'}], 'gc:mossbark_planks', 4),
        'mossbark_planks_to_sticks': shaped('mossbark_sticks', ['#', '#'], {'#': {'item': 'gc:mossbark_planks'}},
                                            'minecraft:stick', 4),
        'glowcap_lantern': shaped('glowcap_to_glowstone', ['##', '##'], {'#': {'item': 'gc:glowcap_cap'}},
                                  'minecraft:glowstone'),
    }


def particle():
    return {'format_version': '1.10.0', 'particle_effect': {
        'description': {'identifier': 'gc:goblin_portal_spark', 'basic_render_parameters': {
            'material': 'particles_add', 'texture': 'textures/particle/goblin_glow'}},
        'components': {
            'minecraft:emitter_rate_instant': {'num_particles': 2},
            'minecraft:emitter_lifetime_once': {'active_time': 0.05},
            'minecraft:emitter_shape_point': {'offset': [0, 0, 0], 'direction': ['math.random(-1,1)', 1, 'math.random(-1,1)']},
            'minecraft:particle_lifetime_expression': {'max_lifetime': 'math.random(0.8, 1.6)'},
            'minecraft:particle_initial_speed': 0.6,
            'minecraft:particle_motion_dynamic': {'linear_acceleration': [0, 0.4, 0], 'linear_drag_coefficient': 1.5},
            'minecraft:particle_appearance_billboard': {
                'size': ['0.12 * (1 - variable.particle_age / variable.particle_lifetime)'] * 2,
                'facing_camera_mode': 'rotate_xyz',
                'uv': {'texture_width': 16, 'texture_height': 16, 'uv': [0, 0], 'uv_size': [16, 16]}},
            'minecraft:particle_appearance_tinting': {'color': [0.45, 1, 0.35, 1]},
            'minecraft:particle_appearance_lighting': {},
        }}}


NOTES = '''
REGNO DEI GOBLIN — 1.3.0
Il Colosso Robot è stato RIMOSSO (non funzionava). Entità, script, modello,
texture, animazioni e uova del robot non fanno più parte dell'addon. Se in un
mondo esisteva già un robot, al caricamento sparisce (entità sconosciuta).

REQUISITI
Bedrock 1.26.30 o superiore (aggiornamento "Chaos Cubed", giugno 2026) con Script
API stabile @minecraft/server 2.8.0: le dimensioni personalizzate sono stabili da
questa versione. Nessun esperimento o Beta API richiesto. Le versioni precedenti di
Minecraft non caricano il Behavior Pack 1.3.0.

1) MATTONI DI MUSCHIO GOBLIN
Ricetta nel banco da lavoro: 9 blocchi di muschio (3×3) = 1 Mattoni di muschio goblin.
Il muschio si moltiplica con la farina d'ossa, quindi è rinnovabile.

2) COSTRUISCI IL PORTALE (come quello del Nether)
Cornice 4 blocchi di base × 5 di altezza, in verticale, verso nord/sud o est/ovest.
Apertura interna 2 × 3 vuota. Gli angoli sono facoltativi: servono 10 mattoni
(14 con gli angoli).

     # # # #        # = Mattoni di muschio goblin
     # . . #        . = aria
     # . . #
     # . . #
     # # # #

3) ACCENDILO
Usa un accendino (acciarino) o una carica di fuoco su un mattone della cornice o
dentro l'apertura. L'apertura si riempie di un portale verde luminoso con
particelle. Se rompi un mattone o un blocco del portale, il portale si spegne.

4) ENTRA
Resta dentro 3 secondi (in Creativa subito). Arrivi nel Regno dei Goblin, davanti
a un portale di ritorno già acceso. I portali restano collegati tra loro: tornando
indietro compari vicino al portale di partenza.

LA DIMENSIONE gc:goblin_realm
Colline di erba goblin, terra goblin e pietra goblin, laghetti, felci e funghi goblin.
Foreste di muschiocorteccia (tronchi coperti di muschio, chiome con barbe di muschio)
e boschetti di fungoluce: funghi giganti con cappelli luminosi che illuminano la notte.
Nel sottosuolo: minerale d'oro goblin (pepite d'oro) e cristalli goblin luminosi
(schegge di ametista). Capanne goblin in assi di muschiocorteccia con tetto di mattoni.
Goblin arcieri e, più raramente, Goblin Colossi con il loro equipaggio popolano il
regno e attaccano i giocatori in Sopravvivenza.
Il terreno viene generato dallo script attorno ai giocatori (raggio 3 chunk), in
pochi secondi, senza bloccare il gioco. Sotto c'è un fondo di bedrock a Y 40.

NUOVI BLOCCHI (Creativa: scheda Natura / Costruzione)
Mattoni di muschio goblin · Erba goblin · Terra goblin · Pietra goblin
Minerale d'oro goblin · Cristallo goblin (luce) · Tronco/Assi/Foglie di muschiocorteccia
Gambo e Cappello di fungoluce (luce) · Germoglio di muschiocorteccia · Spora di fungoluce
Fungo goblin · Felce goblin.
Germoglio e spora crescono da soli o con farina d'ossa, anche nell'Overworld.
Ricette extra: 1 tronco = 4 assi; 2 assi = 4 bastoni; 4 cappelli di fungoluce = 1 pietra
luminosa. Le foglie lasciano cadere germogli e bastoni.

COMANDI UTILI
/give @s gc:goblin_moss_bricks 14
/give @s flint_and_steel
/execute in gc:goblin_realm run tp @s 0 90 0   (se il comando accetta la dimensione)

COLLAUDO NECESSARIO
Verificati con test automatici: struttura JSON/ZIP, ricetta, riconoscimento della
cornice 4×5 su entrambi gli assi e in tutte le posizioni del clic, accensione,
spegnimento, collegamento dei portali, viaggio e generazione del terreno con API
simulate. NON eseguito dentro Minecraft: controlla il Content Log al primo avvio.
Se il portale non si accende: verifica che la cornice sia completa (10 mattoni),
l'apertura vuota e che Minecraft sia 1.26.30+. Se il viaggio fallisce, riprova: la
prima volta la dimensione deve caricare e generare i chunk (qualche secondo).
'''


def lang_lines(lang):
    it = lang == 'it_IT'
    lines = []
    for ident, (i, e, *_rest) in BLOCKS.items():
        lines.append(f'tile.gc:{ident}.name={i if it else e}')
    for ident, (i, e, _c) in PLANTS.items():
        lines.append(f'tile.gc:{ident}.name={i if it else e}')
    lines.append('tile.gc:goblin_portal.name=' + ('Portale goblin' if it else 'Goblin Portal'))
    lines.append('dimension.gc:goblin_realm.name=' + ('Regno dei Goblin' if it else 'Goblin Realm'))
    return lines


def build():
    path = ROOT / 'Goblin-Caravan-Blockbench.zip'
    with zipfile.ZipFile(path) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    # 1. Remove the robot colossus completely.
    for name in list(entries):
        if 'colossus' in name or name.endswith('loot_tables/entities/robot_colossus.json'):
            del entries[name]
    # 2. Scripts.
    for name in list(entries):
        if name.startswith(BP + 'scripts/'):
            del entries[name]
    entries[BP + 'scripts/main.js'] = (ROOT / 'minecraft/main.js').read_bytes()
    entries[BP + 'scripts/goblin_realm.js'] = (ROOT / 'minecraft/goblin_realm.js').read_bytes()
    # 3. Blocks, recipes, loot.
    for ident, (_i, _e, faces, o) in BLOCKS.items():
        entries[BP + f'blocks/{ident}.json'] = encoded(cube_block(ident, faces, o))
    for ident, (_i, _e, comp) in PLANTS.items():
        entries[BP + f'blocks/{ident}.json'] = encoded(plant_block(ident, comp))
    entries[BP + 'blocks/goblin_portal.json'] = encoded(portal_block())
    for name, value in recipes().items():
        entries[BP + f'recipes/{name}.json'] = encoded(value)
    for name, value in loot_tables().items():
        entries[BP + f'loot_tables/blocks/{name}.json'] = encoded(value)
    # 4. Resource pack: textures, atlas, flipbook, sounds, models, particle.
    tex = textures()
    atlas = {}
    for name, data in tex.items():
        entries[RP + TEX + name + '.png'] = data
        entries['textures/blocks/' + name + '.png'] = data
        atlas['gc_' + name] = {'textures': TEX + name}
    entries[RP + 'textures/terrain_texture.json'] = encoded({
        'resource_pack_name': 'goblin_caravan', 'texture_name': 'atlas.terrain',
        'padding': 8, 'num_mip_levels': 4, 'texture_data': atlas})
    entries[RP + 'textures/flipbook_textures.json'] = encoded([{
        'flipbook_texture': TEX + 'goblin_portal', 'atlas_tile': 'gc_goblin_portal',
        'ticks_per_frame': 3, 'blend_frames': True}])
    sounds = {'format_version': '1.1.0'}
    for ident, (*_x, o) in BLOCKS.items():
        sounds['gc:' + ident] = {'sound': o['sound']}
    for ident in PLANTS:
        sounds['gc:' + ident] = {'sound': 'grass'}
    sounds['gc:goblin_portal'] = {'sound': 'glass'}
    entries[RP + 'blocks.json'] = encoded(sounds)
    cross, pane = geometries()
    entries[RP + 'models/blocks/cross.geo.json'] = encoded(cross)
    entries[RP + 'models/blocks/portal_pane.geo.json'] = encoded(pane)
    entries['geometry/blocks/cross.geo.json'] = encoded(cross)
    entries['geometry/blocks/portal_pane.geo.json'] = encoded(pane)
    entries[RP + 'particles/goblin_portal_spark.json'] = encoded(particle())
    entries[RP + 'textures/particle/goblin_glow.png'] = glow_particle()
    # 5. Languages.
    for language in ['it_IT', 'en_US']:
        p = RP + 'texts/' + language + '.lang'
        kept = [l for l in entries[p].decode().splitlines()
                if l.strip() and 'robot_colossus' not in l and not l.startswith(('tile.gc:', 'dimension.gc:'))]
        entries[p] = ('\n'.join(kept + lang_lines(language)) + '\n').encode()
    # 6. Manifests.
    for prefix in [BP, RP]:
        manifest = json.loads(entries[prefix + 'manifest.json'])
        manifest['header']['version'] = VERSION
        manifest['header']['min_engine_version'] = ENGINE
        manifest['header']['description'] = 'Goblin Caravan 1.3.0 — Regno dei Goblin: portale di muschio, nuovi blocchi e alberi'
        for m in manifest['modules']:
            m['version'] = VERSION
        for dep in manifest.get('dependencies', []):
            if 'uuid' in dep:
                dep['version'] = VERSION
            if dep.get('module_name') == '@minecraft/server':
                dep['version'] = SCRIPT_API
        entries[prefix + 'manifest.json'] = encoded(manifest)
    # 7. Notes.
    notes = entries['LEGGIMI.txt'].decode().split('\nCOLOSSO ROBOT — ')[0].split('\nREGNO DEI GOBLIN — ')[0]
    for previous in ['1.1.0', '1.2.0', '1.2.1', '1.2.2', '1.2.3', '1.2.4']:
        notes = notes.replace('GOBLIN CARAVAN — ' + previous, 'GOBLIN CARAVAN — 1.3.0')
    notes = notes.replace('Bedrock 1.21.90+ con Script API stabile @minecraft/server 2.0.0',
                          'Bedrock 1.26.30+ con Script API stabile @minecraft/server 2.8.0')
    notes = notes.rstrip('\n') + '\n' + NOTES
    entries['LEGGIMI.txt'] = entries['addon-source/LEGGIMI.txt'] = notes.encode()
    # 8. Assemble both packs from EXACTLY the bytes exposed in addon-source/.
    addon = {name: archive({n[len(prefix):]: v for n, v in entries.items() if n.startswith(prefix)})
             for prefix, name in [(BP, 'Goblin_Caravan_BP.mcpack'), (RP, 'Goblin_Caravan_RP.mcpack')]}
    addon['LEGGIMI.txt'] = notes.encode()
    path.write_bytes(archive(entries))
    (ROOT / 'Goblin-Caravan.mcaddon').write_bytes(archive(addon))
    print(f'Built 1.3.0: {len(BLOCKS) + len(PLANTS) + 1} blocks, {len(recipes())} recipes, robot colossus removed')


if __name__ == '__main__':
    build()
