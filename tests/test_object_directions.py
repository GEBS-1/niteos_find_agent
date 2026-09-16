import unittest

from app.objects import accept_building_candidate, is_building_grade_title


class ObjectDirectionsTest(unittest.TestCase):
    def test_business_center_is_building_grade(self):
        self.assertTrue(is_building_grade_title("Бизнес-центр Urban", "бизнес центр"))

    def test_factory_is_accepted_for_industry(self):
        gate = accept_building_candidate(
            title="Завод Элекон",
            address="Казань, ул. Короленко, д. 58",
            query="завод",
            sphere="industry",
        )
        self.assertTrue(gate["ok"], gate)

    def test_generic_factory_is_rejected(self):
        gate = accept_building_candidate(
            title="Завод",
            address="Казань",
            query="завод",
            sphere="industry",
        )
        self.assertFalse(gate["ok"], gate)

    def test_closed_map_object_is_rejected(self):
        gate = accept_building_candidate(
            title="Больше не работает: ТЦ Казанский",
            address="Казань, ул. Столярова, д. 7",
            query="торговый центр",
            sphere="commercial",
        )
        self.assertFalse(gate["ok"], gate)

    def test_housing_complex_is_accepted(self):
        gate = accept_building_candidate(
            title="ЖК Савин Хаус",
            address="Казань, ул. Чистопольская, д. 61",
            query="жилой комплекс",
            sphere="housing",
        )
        self.assertTrue(gate["ok"], gate)

    def test_sports_and_medical_are_accepted(self):
        stadium = accept_building_candidate(
            title="Стадион Ак Барс Арена",
            address="Казань, проспект Ямашева, д. 115А",
            query="стадион",
            sphere="sports",
        )
        hospital = accept_building_candidate(
            title="Городская больница №7",
            address="Казань, ул. Чуйкова, д. 54",
            query="больница",
            sphere="social",
        )
        self.assertTrue(stadium["ok"], stadium)
        self.assertTrue(hospital["ok"], hospital)


if __name__ == "__main__":
    unittest.main()
