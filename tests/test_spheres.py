import unittest

from app.spheres import BUILDING_SPHERE_IDS, building_spheres


class BuildingSpheresTest(unittest.TestCase):
    def test_ui_spheres_are_building_only(self):
        ids = [s.id for s in building_spheres()]
        self.assertEqual(ids, list(BUILDING_SPHERE_IDS))
        self.assertNotIn("shops", ids)
        self.assertNotIn("laundry", ids)
        self.assertNotIn("street", ids)

    def test_building_options_do_not_include_business_points(self):
        queries = {o.query for s in building_spheres() for o in s.options}
        self.assertNotIn("прачечная", queries)
        self.assertNotIn("магазин", queries)
        self.assertNotIn("уличное освещение", queries)
        self.assertIn("торговый центр", queries)
        self.assertIn("бизнес центр", queries)
        self.assertIn("промышленное здание", queries)


if __name__ == "__main__":
    unittest.main()
