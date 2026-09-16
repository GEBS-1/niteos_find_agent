import os
import unittest
from unittest.mock import patch

from app.card_audit import (
    apply_card_audit,
    card_audit_payload,
    _normalize_verdict,
)
from app.cost_guard import cheap_mode_enabled, llm_card_audit_enabled, llm_verify_enabled


class CardAuditTests(unittest.TestCase):
    def test_card_audit_on_by_default_even_in_cheap_mode(self):
        with patch.dict(os.environ, {"HUNT_CHEAP_MODE": "1"}, clear=True):
            self.assertTrue(cheap_mode_enabled())
            self.assertTrue(llm_card_audit_enabled())
            self.assertFalse(llm_verify_enabled())

    def test_card_audit_can_be_disabled(self):
        with patch.dict(
            os.environ, {"HUNT_CHEAP_MODE": "1", "HUNT_LLM_CARD_AUDIT": "0"}, clear=True
        ):
            self.assertFalse(llm_card_audit_enabled())

    def test_normalize_reject_keeps_card_as_warn(self):
        audit = _normalize_verdict(
            {
                "verdict": "reject",
                "confidence": 88,
                "object_ok": True,
                "company_ok": False,
                "contacts_ok": False,
                "reason": "ТСЖ на другой улице не оператор БЦ",
                "issues": ["адрес Столярова ≠ Адмиралтейская"],
                "relation_status": "связь не подтверждена",
                "relation_confidence": 12,
                "clear_phone": True,
            },
            allowed_inns={"1656024134"},
            current_inn="1656024134",
        )
        self.assertEqual(audit["verdict"], "warn")
        self.assertTrue(audit["keep_card"])
        company = {
            "inn": "1656024134",
            "stamp": "в работу",
            "score": 93,
            "phones": ["+7 (495) 725-63-57"],
            "object": {
                "title": 'Бизнес-центр "Петрушкин Двор"',
                "relation": {"status": "предположительная связь", "confidence": 70},
            },
            "presence": {
                "checks": [],
                "phone": {"status": "найдено", "value": "+7 (495) 725-63-57"},
            },
        }
        apply_card_audit(company, audit)
        self.assertEqual(company["stamp"], "осторожно")
        self.assertNotEqual(company["stamp"], "стоп")
        self.assertEqual(company["presence"]["phone"]["value"], "")
        self.assertEqual(company["phones"], [])
        self.assertEqual(company["object"]["relation"]["llm_audit"], "warn")
        self.assertTrue(any("перепроверить" in c.lower() for c in company["presence"]["checks"]))

    def test_normalize_swap_upgrades_reject(self):
        audit = _normalize_verdict(
            {
                "verdict": "reject",
                "use_inn": "1657023736",
                "reason": "лучше юрлицо с именем объекта",
                "clear_phone": True,
                "relation_confidence": 80,
            },
            allowed_inns={"1656024134", "1657023736"},
            current_inn="1656024134",
        )
        self.assertTrue(audit["swapped"])
        self.assertEqual(audit["use_inn"], "1657023736")
        self.assertEqual(audit["verdict"], "warn")
        self.assertTrue(audit["keep_card"])

    def test_run_final_uses_ensure_candidates(self):
        from app.card_audit import summarize_owner_candidates

        rows = summarize_owner_candidates(
            [
                {
                    "inn": "1657023736",
                    "source": "dadata",
                    "resolver_score": 71,
                    "party": {"name": "Петрушкин", "address": "Адмиралтейская 3"},
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["inn"], "1657023736")
        payload = card_audit_payload(
            {
                "inn": "1656024134",
                "name": 'ТСЖ "УЛ.СТОЛЯРОВА, Д.7"',
                "address": "ул Столярова, д 7",
                "okved": "68.32.1",
                "object": {
                    "title": 'Бизнес-центр "Петрушкин Двор"',
                    "address": "Адмиралтейская, 3 к1",
                    "relation": {"status": "предположительная", "confidence": 70},
                },
                "presence": {
                    "phone": {"value": "+7 (495) 725-63-57"},
                    "phone_sources": [
                        {"value": "+7 (495) 725-63-57", "source": "поиск: ТСЖ"}
                    ],
                },
                "owner_candidates": [
                    {
                        "inn": "1657023736",
                        "source": "dadata",
                        "resolver_score": 71,
                        "party": {
                            "name": 'ООО "Электронный рынок Петрушкин Двор"',
                            "address": "Адмиралтейская 3",
                            "okved": "68.20",
                        },
                    }
                ],
            },
            query="бизнес центр",
            city="Казань",
        )
        self.assertEqual(payload["query"], "бизнес центр")
        inns = {row["inn"] for row in payload["candidates"]}
        self.assertIn("1656024134", inns)
        self.assertIn("1657023736", inns)


if __name__ == "__main__":
    unittest.main()
