from app.providers.known_public_finance import known_public_finance


def test_known_public_finance_for_gazprom_transgaz_kazan():
    finance = known_public_finance("1600000036")

    assert finance is not None
    assert finance["revenue"] == 46_539_346_000
    assert finance["profit"] == 101_701_000
    assert finance["source"].startswith("https://companies.rbc.ru/")


def test_known_public_finance_for_rgs_kazan():
    finance = known_public_finance("7725642985")

    assert finance is not None
    assert finance["period"] == "2025"
    assert finance["revenue"] == 402_157_000
    assert finance["profit"] == 97_524_000
