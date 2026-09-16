from app.providers.cadastre_http import _first_payload, _pick


def test_first_payload_accepts_items_properties():
    data = {"items": [{"properties": {"cad_num": "16:50:1:2"}}]}
    assert _first_payload(data) == {"cad_num": "16:50:1:2"}


def test_pick_accepts_nested_owner_inn():
    data = {"owner": {"inn": "1655000000"}}
    assert _pick(data, "right_holder.inn", "owner.inn") == "1655000000"
