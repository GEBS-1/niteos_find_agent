import unittest

from app.contacts import _object_site_belongs


class _Response:
    status_code = 200
    text = "<html><body>Azimut yachts official dealer and boats catalog</body></html>"


class _Client:
    async def get(self, *_args, **_kwargs):
        return _Response()


class ObjectContactsTest(unittest.IsolatedAsyncioTestCase):
    async def test_same_brand_without_city_or_type_is_not_object_site(self):
        ok = await _object_site_belongs(
            _Client(),
            "https://azimutyachts.com/en",
            obj_title="Azimut отель Казань",
            city="Казань",
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
