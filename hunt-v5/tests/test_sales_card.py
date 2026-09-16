from app.services.sales_card import actionable_people, lighting_score

def test_people_without_contacts_are_hidden():
    people = [
        {"full_name":"A", "role":"chief_engineer", "contacts":[]},
        {"full_name":"B", "role":"general_director", "contacts":[{"type":"phone","value":"+7 1","status":"confirmed"}]},
    ]
    assert [p["full_name"] for p in actionable_people(people)] == ["B"]

def test_lighting_score_rewards_road_visible_facade():
    r = lighting_score(photo_url="x", panorama_url="y", road_visible=True, facade_area_signal=True, entrance_signal=True, architectural_rhythm_signal=True, signage_signal=True)
    assert r["score"] == 100
    assert r["status"] == "high"
