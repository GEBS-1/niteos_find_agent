import unittest

from app.objects import _photo_matches_building, object_photo_ok


class ObjectPhotoTests(unittest.TestCase):
    def test_rejects_service_placeholders_and_search_thumbnails(self):
        self.assertFalse(object_photo_ok("https://d-assets.2gis.ru/default-share.png"))
        self.assertFalse(object_photo_ok("https://avatars.mds.yandex.net/i?id=abc123"))
        self.assertFalse(object_photo_ok("https://i.ytimg.com/vi/abc/maxresdefault.jpg"))

    def test_accepts_yandex_maps_org_gallery_photo(self):
        self.assertTrue(
            object_photo_ok(
                "https://avatars.mds.yandex.net/get-altay/9663145/2a000001898425371a2b535c73021a6b09d4/orig"
            )
        )

    def test_photo_url_must_match_building_identity(self):
        self.assertTrue(
            _photo_matches_building(
                "https://example.com/media/mega-kazan-fasad.jpg",
                "Торговый центр Мега",
            )
        )
        self.assertFalse(
            _photo_matches_building(
                "https://example.com/media/random-cafe-interior.jpg",
                "Торговый центр Мега",
            )
        )


if __name__ == "__main__":
    unittest.main()
