from app.services.contact_roles import rank_people


def test_engineer_is_ranked_above_general_director():
    p = rank_people([
        {"full_name":"CEO","role":"general_director"},
        {"full_name":"Engineer","role":"chief_engineer"},
    ])
    assert p[0]["role"] == "chief_engineer"
