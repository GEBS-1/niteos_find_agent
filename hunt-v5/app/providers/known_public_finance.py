from __future__ import annotations


_FINANCE = {
    "1600000036": {
        "revenue": 46_539_346_000,
        "profit": 101_701_000,
        "employees": None,
        "period": "последняя доступная публичная запись",
        "source": "https://companies.rbc.ru/id/1021603624921-ooo-gazprom-transgaz-kazan/",
        "summary": (
            "Финансовые показатели взяты из публичного профиля компании. "
            "Период в источнике нужно сверить по ссылке перед коммерческим предложением."
        ),
    }
    ,
    "7725642985": {
        "revenue": 402_157_000,
        "profit": 97_524_000,
        "employees": None,
        "period": "2025",
        "source": "https://companies.rbc.ru/id/1087746876821-ooo-rgs-kazan/",
        "summary": (
            "Финансовые показатели взяты из публичного профиля РБК Компании: "
            "выручка и прибыль за 2025 год."
        ),
    },
}


def known_public_finance(inn: str) -> dict | None:
    row = _FINANCE.get(str(inn or "").strip())
    return dict(row) if row else None
