import unittest

from app.owners import _candidate_score


def cand(name, address="", okved="", source="dadata"):
    return {
        "source": source,
        "suggest": {
            "value": name,
            "data": {
                "name": name,
                "address": {"value": address},
                "okved": okved,
            },
        },
    }


class OwnerScoringTests(unittest.TestCase):
    def test_school_number_and_profile_win(self):
        score, reasons = _candidate_score(
            cand(
                'МБОУ "Средняя общеобразовательная школа № 12"',
                "г Казань, ул Ленина, д 5",
                "85.14",
            ),
            title="Школа №12",
            address="г Казань, ул Ленина, д 5",
            city="Казань",
        )
        self.assertGreaterEqual(score, 80)
        self.assertTrue(reasons)

    def test_mall_management_company_beats_tenant(self):
        uk_score, _ = _candidate_score(
            cand('ООО "Парк Управление"', "г Казань, ул Победы, д 10", "68.32"),
            title='ТЦ "Парк"',
            address="г Казань, ул Победы, д 10",
            city="Казань",
        )
        tenant_score, _ = _candidate_score(
            cand('ООО "Магазин Парк"', "г Казань, ул Победы, д 10", "47.19"),
            title='ТЦ "Парк"',
            address="г Казань, ул Победы, д 10",
            city="Казань",
        )
        self.assertGreater(uk_score, tenant_score)

    def test_warehouse_profile_gets_evidence(self):
        score, reasons = _candidate_score(
            cand('ООО "Восток Логистик"', "г Казань, ул Складская, д 7", "52.10"),
            title='Складской комплекс "Восток"',
            address="г Казань, ул Складская, д 7",
            city="Казань",
        )
        self.assertGreaterEqual(score, 70)
        self.assertTrue(any("склад" in r.lower() or "оквэд" in r.lower() for r in reasons))


if __name__ == "__main__":
    unittest.main()
