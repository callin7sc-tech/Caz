"""Run: python -B tests/test_realm_assets.py. Checks the built archives; no Minecraft runtime."""
import io
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BP = 'addon-source/Goblin_Caravan_BP/'
RP = 'addon-source/Goblin_Caravan_RP/'


def read_zip(data):
    with zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data) as z:
        return {n: z.read(n) for n in z.namelist()}


class RealmAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        before = (ROOT / 'Goblin-Caravan.mcaddon').read_bytes(), (ROOT / 'Goblin-Caravan-Blockbench.zip').read_bytes()
        subprocess.run([sys.executable, '-B', str(ROOT / 'minecraft/build_realm.py')], check=True, capture_output=True)
        cls.deterministic = before == ((ROOT / 'Goblin-Caravan.mcaddon').read_bytes(), (ROOT / 'Goblin-Caravan-Blockbench.zip').read_bytes())
        cls.bb = read_zip(ROOT / 'Goblin-Caravan-Blockbench.zip')
        addon = read_zip(ROOT / 'Goblin-Caravan.mcaddon')
        cls.addon = addon
        cls.bp = read_zip(addon['Goblin_Caravan_BP.mcpack'])
        cls.rp = read_zip(addon['Goblin_Caravan_RP.mcpack'])

    def test_build_is_deterministic(self):
        self.assertTrue(self.deterministic)

    def test_robot_colossus_is_gone(self):
        for files in (self.bb, self.bp, self.rp):
            for name, data in files.items():
                self.assertNotIn('colossus', name.lower())
                if name.endswith(('.json', '.js', '.lang')):
                    self.assertNotIn(b'robot_colossus', data, name)
                    self.assertNotIn(b'colossus.js', data, name)

    def test_goblins_are_kept(self):
        for n in ['entities/archer.json', 'entities/giant.json']:
            self.assertIn(n, self.bp)
        for n in ['models/entity/giant.geo.json', 'models/entity/archer.geo.json', 'entity/giant.entity.json']:
            self.assertIn(n, self.rp)
        self.assertIn('giant.bbmodel', self.bb)

    def test_packs_match_sources(self):
        for prefix, pack in [(BP, self.bp), (RP, self.rp)]:
            src = {n[len(prefix):]: v for n, v in self.bb.items() if n.startswith(prefix)}
            self.assertEqual(src, pack)

    def test_all_json_parses(self):
        for pack in (self.bp, self.rp):
            for name, data in pack.items():
                if name.endswith('.json'):
                    json.loads(data)

    def test_manifests_require_stable_custom_dimensions(self):
        bp = json.loads(self.bp['manifest.json'])
        rp = json.loads(self.rp['manifest.json'])
        self.assertEqual(bp['header']['version'], [1, 3, 1])
        self.assertEqual(bp['header']['min_engine_version'], [1, 26, 30])
        api = [d for d in bp['dependencies'] if d.get('module_name') == '@minecraft/server'][0]
        self.assertEqual(api['version'], '2.8.0')
        self.assertNotIn('beta', json.dumps(bp))
        self.assertEqual([d for d in bp['dependencies'] if 'uuid' in d][0]['uuid'], rp['header']['uuid'])
        self.assertEqual(bp['header']['uuid'], '3197919a-d1f6-4fca-a430-a8343662c3b1')

    def test_moss_brick_recipe_is_nine_moss_blocks(self):
        r = json.loads(self.bp['recipes/goblin_moss_bricks.json'])['minecraft:recipe_shaped']
        self.assertEqual(r['pattern'], ['###', '###', '###'])
        self.assertEqual(r['key']['#']['item'], 'minecraft:moss_block')
        self.assertEqual(r['result']['item'], 'gc:goblin_moss_bricks')
        self.assertIn('crafting_table', r['tags'])

    def test_blocks_textures_and_names(self):
        terrain = json.loads(self.rp['textures/terrain_texture.json'])['texture_data']
        sounds = json.loads(self.rp['blocks.json'])
        langs = {l: self.rp[f'texts/{l}.lang'].decode() for l in ['it_IT', 'en_US']}
        script = self.bp['scripts/goblin_realm.js'].decode()
        blocks = {}
        for name, data in self.bp.items():
            if name.startswith('blocks/'):
                b = json.loads(data)['minecraft:block']
                ident = b['description']['identifier']
                blocks[ident] = b
                for inst in b['components']['minecraft:material_instances'].values():
                    tex = terrain[inst['texture']]['textures']
                    self.assertIn(tex + '.png', self.rp)
                    Image.open(io.BytesIO(self.rp[tex + '.png'])).verify()
                self.assertIn(ident, sounds)
                for text in langs.values():
                    self.assertIn(f'tile.{ident}.name=', text)
                loot = b['components'].get('minecraft:loot')
                if loot:
                    self.assertIn(loot, self.bp)
                # Minecraft (format >= 1.21.90) drops a block that has material
                # instances but no geometry: this is what hid 11 blocks in 1.3.0.
                geo = b['components'].get('minecraft:geometry')
                self.assertTrue(geo, ident + ' has no minecraft:geometry')
                if geo != 'minecraft:geometry.full_block':
                    self.assertTrue(any(geo.encode() in v for n, v in self.rp.items() if n.startswith('models/blocks/')))
                for comp in b['components']:
                    if comp.startswith('gc:'):
                        self.assertIn(f"registerCustomComponent('{comp}'", script)
        # Every block the script places exists in the pack.
        for ident in set(re.findall(r"'(gc:[a-z_]+)'", script)):
            if ident in ('gc:goblin_realm', 'gc:axis', 'gc:sapling', 'gc:portal_fx', 'gc:goblin_portal_spark',
                         'gc:archer', 'gc:giant', 'gc:portal/'):
                continue
            self.assertIn(ident, blocks, ident)
        self.assertEqual(len(blocks), 16)
        for ident in ('gc:mossbark_log', 'gc:glowcap_stem'):
            traits = blocks[ident]['description']['traits']['minecraft:placement_position']
            self.assertEqual(traits['enabled_states'], ['minecraft:block_face'])
            self.assertEqual(len(blocks[ident]['permutations']), 2)
        # Placement filters only use block ids that exist in Bedrock.
        for ident in ('gc:mossbark_sapling', 'gc:glowcap_sprout', 'gc:goblin_fern', 'gc:goblin_mushroom'):
            allowed = blocks[ident]['components']['minecraft:placement_filter']['conditions'][0]['block_filter']
            self.assertNotIn('minecraft:rooted_dirt', allowed)
            self.assertIn('minecraft:dirt_with_roots', allowed)
        portal = blocks['gc:goblin_portal']
        self.assertEqual(portal['description']['states'], {'gc:axis': ['x', 'z']})
        self.assertFalse(portal['components']['minecraft:collision_box'])
        self.assertIn('gc:goblin_portal_spark', self.rp['particles/goblin_portal_spark.json'].decode())

    def test_recipes_have_unlock_data(self):
        # 1.20.10+ recipes without "unlock" are rejected by Minecraft.
        for name, data in self.bp.items():
            if name.startswith('recipes/'):
                recipe = json.loads(data)
                body = next(v for k, v in recipe.items() if k.startswith('minecraft:recipe_'))
                self.assertTrue(body.get('unlock'), name)

    def test_giant_float_properties_have_float_defaults(self):
        giant = json.loads(self.bp['entities/giant.json'])['minecraft:entity']['description']['properties']
        for name, prop in giant.items():
            if prop['type'] == 'float':
                self.assertIsInstance(prop['default'], float, name)
                self.assertTrue(all(isinstance(v, float) for v in prop['range']), name)
        # The raw JSON must literally contain a decimal point.
        self.assertIn(b'"default": 0.0', self.bp['entities/giant.json'])

    def test_portal_texture_is_animated(self):
        flip = json.loads(self.rp['textures/flipbook_textures.json'])[0]
        self.assertEqual(flip['atlas_tile'], 'gc_goblin_portal')
        im = Image.open(io.BytesIO(self.rp[flip['flipbook_texture'] + '.png']))
        self.assertEqual(im.width, 16)
        self.assertEqual(im.height % 16, 0)
        self.assertGreater(im.height // 16, 1)

    def test_scripts_are_wired(self):
        main = self.bp['scripts/main.js'].decode()
        self.assertIn("from './goblin_realm.js'", main)
        self.assertIn('REALM', main)
        manifest = json.loads(self.bp['manifest.json'])
        self.assertEqual([m for m in manifest['modules'] if m['type'] == 'script'][0]['entry'], 'scripts/main.js')
        for js in ['scripts/main.js', 'scripts/goblin_realm.js']:
            subprocess.run(['node', '--check', '--input-type=module'], input=self.bp[js], check=True)

    def test_notes_explain_the_portal(self):
        notes = self.addon['LEGGIMI.txt'].decode()
        for words in ['9 blocchi di muschio', '4 blocchi di base', '5 di altezza', 'accendino', 'RIMOSSO', '1.26.30']:
            self.assertIn(words, notes)
        self.assertNotIn('COLOSSO ROBOT —', notes)


if __name__ == '__main__':
    unittest.main()
