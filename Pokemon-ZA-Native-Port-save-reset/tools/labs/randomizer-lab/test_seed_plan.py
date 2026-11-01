import unittest
from seed_plan import pick,plan,ROOT
class SeedTests(unittest.TestCase):
    def test_iteration_order_independent(self):
        pool=[{'species':i,'form':0} for i in range(1,235)]
        self.assertEqual(pick('42','wild','slot',pool),pick('42','wild','slot',list(reversed(pool))))
    def test_domain_and_seed_change_results(self):
        pool=list(range(100000));a=pick('seed','wild','id',pool)
        self.assertNotEqual(a,pick('other','wild','id',pool));self.assertNotEqual(a,pick('seed','trainer','id',pool))
    def test_excludes_original_and_empty_pool(self):
        self.assertEqual(pick('42','wild','slot',[1,2],1),2)
        with self.assertRaises(ValueError):pick('42','wild','slot',[1],1)
    def test_unicode_seed_normalization(self):
        self.assertEqual(pick('e\u0301','x','y',list(range(100))),pick('\u00e9','x','y',list(range(100))))
    def test_real_plan_reproducible_and_marks_gaps(self):
        if not (ROOT/'personal-catalog.json').exists():self.skipTest('Requires the local read-only scan outputs')
        a=plan('Tomer-2026');b=plan('Tomer-2026');c=plan('Tomer-2027')
        self.assertEqual(a,b);self.assertNotEqual(a['plan_sha256'],c['plan_sha256'])
        self.assertFalse(a['applies_changes'])
        self.assertTrue(any(i['domain']=='rogue-mega' and i['status']=='manual-review' for i in a['items']))
        self.assertTrue(any(i['domain']=='trainer-mega' for i in a['items']))
if __name__=='__main__':unittest.main()
