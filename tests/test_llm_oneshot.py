import os
import unittest
from unittest.mock import patch

from app.cost_guard import llm_oneshot_enabled
from app.llm_oneshot import (
    _looks_fake_inn,
    _looks_fake_phone,
    _looks_guessed_email,
    map_oneshot_card,
)


class LlmOneshotTests(unittest.TestCase):
    def test_oneshot_flag_default_on(self):
        with patch.dict(os.environ, {"HUNT_CHEAP_MODE": "1"}, clear=True):
            self.assertTrue(llm_oneshot_enabled())

    def test_oneshot_can_disable(self):
        with patch.dict(os.environ, {"HUNT_LLM_ONESHOT": "0"}, clear=True):
            self.assertFalse(llm_oneshot_enabled())

    def test_rejects_fake_inn_and_phone(self):
        self.assertTrue(_looks_fake_inn("1651000000"))
        self.assertTrue(_looks_fake_phone("+7 (843) 222-22-22"))
        self.assertTrue(_looks_guessed_email("info@compressormash.ru", "http://compressormash.ru/"))

    def test_map_card_strips_fakes(self):
        card = map_oneshot_card(
            {
                "object_title": "АО Казанькомпрессормаш",
                "object_address": "Казань",
                "company_name": "АО Казанькомпрессормаш",
                "inn": "1651000000",
                "phone": "+7 (843) 222-22-22",
                "email": "info@compressormash.ru",
                "site": "http://compressormash.ru/",
                "vk": "",
                "confidence": 50,
                "notes": "draft",
            },
            query="Казанькомпрессормаш",
            city="Казань",
        )
        self.assertTrue(str(card["inn"]).startswith("OBJ-"))
        self.assertEqual(card["presence"]["phone"]["value"], "")
        self.assertEqual(card["presence"]["email"]["value"], "")
        self.assertEqual(card["presence"]["site"]["value"], "http://compressormash.ru/")

    def test_map_keeps_real_looking_fields(self):
        card = map_oneshot_card(
            {
                "object_title": 'БЦ "Петрушкин Двор"',
                "company_name": "ООО Тест",
                "inn": "1657023736",
                "phone": "+7 (843) 567-89-01",
                "email": "sales@petrushkin-dvor.ru",
                "site": "https://petrushkin-dvor.ru",
                "vk": "https://vk.com/example",
                "confidence": 72,
                "notes": "ok",
                "sources": {"inn": "checko", "phone": "site"},
            },
            query="Петрушкин Двор",
            city="Казань",
        )
        self.assertEqual(card["inn"], "1657023736")
        self.assertIn("567-89-01", card["presence"]["phone"]["value"])
        self.assertEqual(card["presence"]["vk_company"]["value"], "https://vk.com/example")

    def test_map_people_finance_founders(self):
        card = map_oneshot_card(
            {
                "object_title": "Казанькомпрессормаш",
                "company_name": 'АО "КАЗАНЬКОМПРЕССОРМАШ"',
                "inn": "1660004878",
                "management": 'ООО "УК ГРУППА ГМС"',
                "management_post": "управляющая организация",
                "phone": "+7 (843) 291-98-09",
                "site": "http://compressormash.ru/",
                "revenue": "12 млрд",
                "profit": "800 млн",
                "expense": "11 млрд",
                "finance_year": "2023",
                "founders": [{"name": "ООО Холдинг", "share": "100%", "type": "LEGAL"}],
                "beneficiaries": [{"name": "Иванов Иван Иванович", "share": "60%"}],
                "people": [
                    {
                        "name": "Петров Пётр Петрович",
                        "role": "генеральный директор",
                        "phone": "+7 (843) 111-22-33",
                        "email": "petrov@hms.ru",
                        "vk": "https://vk.com/id123",
                        "source": "checko",
                        "why": "ЛПР по решению",
                    },
                    {
                        "name": "Сидоров Алексей",
                        "role": "коммерческий директор",
                        "phone": "",
                        "email": "sales@hms-kkm.ru",
                        "source": "сайт",
                        "why": "КП по поставкам",
                    },
                ],
                "confidence": 80,
                "notes": "ok",
                "sources": {"finance": "checko", "people": "open", "founders": "zachestnyibiznes"},
            },
            query="Казанькомпрессормаш",
            city="Казань",
        )
        self.assertEqual(card["management"], "Петров Пётр Петрович")
        self.assertIn("111-22-33", card["presence"]["phone"]["value"])
        self.assertEqual(len(card["people_contacts"]), 2)
        # Finance from LLM is intentionally NOT mapped (registries only)
        self.assertIsNone(card["revenue"])
        self.assertEqual(card["revenue_text"], "—")
        self.assertTrue(any("Иванов" in f for f in card["founders"]))
        self.assertEqual(card["presence"]["vk_lpr"]["value"], "https://vk.com/id123")
        self.assertIn("ЛПР/контакты", " ".join(card["checks"]))


if __name__ == "__main__":
    unittest.main()
