"""Meaningful offline checks of location semantics and final-run reconstruction."""
import copy, json, unittest
from pathlib import Path
from forecast import ROOT, build_forecast


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.encounters = [dict(id='enc1', devNo=953, formNo=0, minLevel=3, maxLevel=5,
            wazaList=None, activationCondition=[])]
        self.personal = [dict(species=953, form=0, national=967, name='Cyclizar',
            learnset=[dict(move=33, level=1), dict(move=784, level=5), dict(move=99, level=60)])]
        self.spawner = dict(id='sp1', appearanceSpawnerObjectInfoList=[dict(objectName='obj',
            createScenePath='scene', zoneInfo=dict(zoneId='zone1'))],
            encountDataInfoList=[dict(encountDataId='enc1', weight=10, additionalLevel=0,
                appearedTimeCondition=1, activationCondition=[dict(phase=100)])])

    def run_case(self, spawners=None, encounters=None):
        return build_forecast(encounters or self.encounters, spawners or [self.spawner],
            [], self.personal, [dict(zoneId='zone1')])

    def test_internal_and_national_are_distinct(self):
        result = self.run_case()['groups'][0]['species_forms'][0]
        self.assertEqual((result['species'], result['national']), (953, 967))

    def test_conditions_retained_and_moves_are_superset(self):
        e = self.run_case()['groups'][0]['encounters'][0]
        self.assertEqual(e['spawn_link']['appearedTimeCondition'], 1)
        self.assertEqual(e['spawn_link']['activationCondition'], [dict(phase=100)])
        self.assertEqual(e['move_candidates'], [33, 784])
        self.assertFalse(e['move_candidates_are_exact'])

    def test_relative_scene_is_not_inferred_from_spawner_name(self):
        sp = copy.deepcopy(self.spawner)
        sp['id'] = 'id_spn_a0102_w01_looks_like_zone'
        sp['appearanceSpawnerObjectInfoList'] = [dict(objectName='obj', createScenePath='./')]
        result = self.run_case([sp])
        self.assertEqual(result['groups'][0]['kind'], 'unlocated')
        self.assertEqual(result['counts']['unlocated_spawners'], 1)

    def test_one_spawner_in_two_zones_is_preserved(self):
        sp = copy.deepcopy(self.spawner)
        sp['appearanceSpawnerObjectInfoList'].append(dict(objectName='other', zoneInfo=dict(zoneId='zone2')))
        result = self.run_case([sp])
        self.assertEqual(result['counts']['zone_groups'], 2)
        self.assertEqual(result['counts']['referenced_encounter_rows'], 1)

    def test_missing_reference_reported(self):
        sp = copy.deepcopy(self.spawner)
        sp['encountDataInfoList'][0]['encountDataId'] = 'missing'
        self.assertEqual(self.run_case([sp])['counts']['missing_encounter_links'], 1)

    def test_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError):
            self.run_case(encounters=self.encounters * 2)

    def test_verified_seed_rock_provider_and_accounting(self):
        f = json.loads((ROOT/'evidence/shader-prewarm-research-20261028/area-forecast.json').read_bytes())
        self.assertEqual(f['wild_sha256'], '243339faa8a533439ffcac96c45c23797b1560b7fa6b046590c44ed6cb67d326')
        self.assertEqual(f['seed'], '6177047620')
        zone = next(x for x in f['groups'] if x['id']=='a0102_w01')
        provider = [e for e in zone['encounters'] if e['id'] in
            ('ect_a0102_w01_v01_z659_tuto', 'ect_a0102_w01_v01_z659')]
        self.assertTrue(provider)
        self.assertEqual({e['species'] for e in provider}, {706})
        self.assertTrue(all(784 in e['move_candidates'] for e in provider))
        c = f['counts']
        self.assertEqual(c['referenced_encounter_rows'] + c['unreferenced_encounter_rows'], c['encounter_rows'])
        self.assertEqual(c['missing_encounter_links'], 0)


if __name__ == '__main__':
    unittest.main()
