"""Geography tree: Russia → federal districts → regions → cities."""
from __future__ import annotations

from typing import Any

# Each FO: id, title, regions[{id, title, dadata_region, cities[str,...]}]
FEDERAL_DISTRICTS: tuple[dict[str, Any], ...] = (
    {
        "id": "cfo",
        "title": "Центральный ФО",
        "regions": (
            {
                "id": "moscow",
                "title": "Москва",
                "dadata_region": "Москва",
                "cities": ("Москва",),
            },
            {
                "id": "mosobl",
                "title": "Московская область",
                "dadata_region": "Московская",
                "cities": (
                    "Подольск",
                    "Химки",
                    "Балашиха",
                    "Мытищи",
                    "Королёв",
                    "Люберцы",
                    "Красногорск",
                    "Электросталь",
                    "Коломна",
                    "Одинцово",
                    "Домодедово",
                    "Серпухов",
                    "Щёлково",
                    "Раменское",
                    "Ногинск",
                    "Пушкино",
                    "Жуковский",
                    "Сергиев Посад",
                    "Орехово-Зуево",
                    "Долгопрудный",
                    "Реутов",
                    "Клин",
                    "Чехов",
                    "Наро-Фоминск",
                    "Егорьевск",
                    "Видное",
                    "Истра",
                    "Дмитров",
                    "Павловский Посад",
                ),
            },
            {
                "id": "tula",
                "title": "Тульская область",
                "dadata_region": "Тульская",
                "cities": ("Тула", "Новомосковск", "Алексин"),
            },
            {
                "id": "tver",
                "title": "Тверская область",
                "dadata_region": "Тверская",
                "cities": ("Тверь",),
            },
            {
                "id": "yaroslavl",
                "title": "Ярославская область",
                "dadata_region": "Ярославская",
                "cities": ("Ярославль", "Рыбинск", "Переславль-Залесский"),
            },
            {
                "id": "ryazan",
                "title": "Рязанская область",
                "dadata_region": "Рязанская",
                "cities": ("Рязань",),
            },
            {
                "id": "kaluga",
                "title": "Калужская область",
                "dadata_region": "Калужская",
                "cities": ("Калуга", "Обнинск"),
            },
            {
                "id": "vladimir",
                "title": "Владимирская область",
                "dadata_region": "Владимирская",
                "cities": ("Владимир", "Ковров", "Муром"),
            },
            {
                "id": "voronezh",
                "title": "Воронежская область",
                "dadata_region": "Воронежская",
                "cities": ("Воронеж",),
            },
            {
                "id": "belgorod",
                "title": "Белгородская область",
                "dadata_region": "Белгородская",
                "cities": ("Белгород", "Старый Оскол", "Губкин"),
            },
            {
                "id": "kursk",
                "title": "Курская область",
                "dadata_region": "Курская",
                "cities": ("Курск",),
            },
            {
                "id": "lipetsk",
                "title": "Липецкая область",
                "dadata_region": "Липецкая",
                "cities": ("Липецк", "Елец"),
            },
            {
                "id": "tambov",
                "title": "Тамбовская область",
                "dadata_region": "Тамбовская",
                "cities": ("Тамбов",),
            },
            {
                "id": "bryansk",
                "title": "Брянская область",
                "dadata_region": "Брянская",
                "cities": ("Брянск",),
            },
            {
                "id": "orel",
                "title": "Орловская область",
                "dadata_region": "Орловская",
                "cities": ("Орёл",),
            },
            {
                "id": "smolensk",
                "title": "Смоленская область",
                "dadata_region": "Смоленская",
                "cities": ("Смоленск",),
            },
            {
                "id": "ivanovo",
                "title": "Ивановская область",
                "dadata_region": "Ивановская",
                "cities": ("Иваново",),
            },
            {
                "id": "kostroma",
                "title": "Костромская область",
                "dadata_region": "Костромская",
                "cities": ("Кострома",),
            },
        ),
    },
    {
        "id": "szfo",
        "title": "Северо-Западный ФО",
        "regions": (
            {
                "id": "spb",
                "title": "Санкт-Петербург",
                "dadata_region": "Санкт-Петербург",
                "cities": (
                    "Санкт-Петербург",
                    "Колпино",
                    "Пушкин",
                    "Петергоф",
                    "Кронштадт",
                ),
            },
            {
                "id": "lenobl",
                "title": "Ленинградская область",
                "dadata_region": "Ленинградская",
                "cities": (
                    "Гатчина",
                    "Выборг",
                    "Сосновый Бор",
                    "Тихвин",
                    "Кириши",
                    "Всеволожск",
                ),
            },
            {
                "id": "kaliningrad",
                "title": "Калининградская область",
                "dadata_region": "Калининградская",
                "cities": ("Калининград",),
            },
            {
                "id": "murmansk",
                "title": "Мурманская область",
                "dadata_region": "Мурманская",
                "cities": ("Мурманск",),
            },
            {
                "id": "arkhangelsk",
                "title": "Архангельская область",
                "dadata_region": "Архангельская",
                "cities": ("Архангельск",),
            },
            {
                "id": "vologda",
                "title": "Вологодская область",
                "dadata_region": "Вологодская",
                "cities": ("Вологда", "Череповец"),
            },
            {
                "id": "karelia",
                "title": "Карелия",
                "dadata_region": "Карелия",
                "cities": ("Петрозаводск",),
            },
            {
                "id": "komi",
                "title": "Коми",
                "dadata_region": "Коми",
                "cities": ("Сыктывкар",),
            },
            {
                "id": "pskov",
                "title": "Псковская область",
                "dadata_region": "Псковская",
                "cities": ("Псков",),
            },
            {
                "id": "novgorod",
                "title": "Новгородская область",
                "dadata_region": "Новгородская",
                "cities": ("Великий Новгород",),
            },
        ),
    },
    {
        "id": "pfo",
        "title": "Приволжский ФО",
        "regions": (
            {
                "id": "tatarstan",
                "title": "Татарстан",
                "dadata_region": "Татарстан",
                "cities": (
                    "Казань",
                    "Набережные Челны",
                    "Нижнекамск",
                    "Альметьевск",
                    "Зеленодольск",
                    "Бугульма",
                    "Елабуга",
                    "Чистополь",
                    "Лениногорск",
                    "Азнакаево",
                    "Нурлат",
                ),
            },
            {
                "id": "bashkortostan",
                "title": "Башкортостан",
                "dadata_region": "Башкортостан",
                "cities": (
                    "Уфа",
                    "Стерлитамак",
                    "Салават",
                    "Нефтекамск",
                    "Октябрьский",
                ),
            },
            {
                "id": "nnov",
                "title": "Нижегородская область",
                "dadata_region": "Нижегородская",
                "cities": ("Нижний Новгород",),
            },
            {
                "id": "samara",
                "title": "Самарская область",
                "dadata_region": "Самарская",
                "cities": ("Самара", "Тольятти"),
            },
            {
                "id": "perm",
                "title": "Пермский край",
                "dadata_region": "Пермский",
                "cities": ("Пермь",),
            },
            {
                "id": "saratov",
                "title": "Саратовская область",
                "dadata_region": "Саратовская",
                "cities": ("Саратов", "Энгельс", "Балаково"),
            },
            {
                "id": "udmurtia",
                "title": "Удмуртия",
                "dadata_region": "Удмуртская",
                "cities": ("Ижевск",),
            },
            {
                "id": "chuvashia",
                "title": "Чувашия",
                "dadata_region": "Чувашская",
                "cities": ("Чебоксары",),
            },
            {
                "id": "mariel",
                "title": "Марий Эл",
                "dadata_region": "Марий Эл",
                "cities": ("Йошкар-Ола",),
            },
            {
                "id": "mordovia",
                "title": "Мордовия",
                "dadata_region": "Мордовия",
                "cities": ("Саранск",),
            },
            {
                "id": "orenburg",
                "title": "Оренбургская область",
                "dadata_region": "Оренбургская",
                "cities": ("Оренбург", "Орск"),
            },
            {
                "id": "penza",
                "title": "Пензенская область",
                "dadata_region": "Пензенская",
                "cities": ("Пенза",),
            },
            {
                "id": "ulyanovsk",
                "title": "Ульяновская область",
                "dadata_region": "Ульяновская",
                "cities": ("Ульяновск", "Димитровград"),
            },
            {
                "id": "kirov",
                "title": "Кировская область",
                "dadata_region": "Кировская",
                "cities": ("Киров",),
            },
        ),
    },
    {
        "id": "ufo",
        "title": "Уральский ФО",
        "regions": (
            {
                "id": "sverdlovsk",
                "title": "Свердловская область",
                "dadata_region": "Свердловская",
                "cities": (
                    "Екатеринбург",
                    "Нижний Тагил",
                    "Каменск-Уральский",
                    "Первоуральск",
                    "Серов",
                ),
            },
            {
                "id": "chelyabinsk",
                "title": "Челябинская область",
                "dadata_region": "Челябинская",
                "cities": ("Челябинск", "Магнитогорск", "Миасс", "Златоуст", "Копейск"),
            },
            {
                "id": "tyumen",
                "title": "Тюменская область",
                "dadata_region": "Тюменская",
                "cities": ("Тюмень",),
            },
            {
                "id": "hmao",
                "title": "Ханты-Мансийский АО",
                "dadata_region": "Ханты-Мансийский",
                "cities": ("Сургут", "Нижневартовск", "Нефтеюганск", "Ханты-Мансийск"),
            },
            {
                "id": "yanao",
                "title": "Ямало-Ненецкий АО",
                "dadata_region": "Ямало-Ненецкий",
                "cities": ("Новый Уренгой", "Ноябрьск", "Салехард"),
            },
        ),
    },
    {
        "id": "sfo",
        "title": "Сибирский ФО",
        "regions": (
            {
                "id": "novosib",
                "title": "Новосибирская область",
                "dadata_region": "Новосибирская",
                "cities": ("Новосибирск",),
            },
            {
                "id": "krasnoyarsk",
                "title": "Красноярский край",
                "dadata_region": "Красноярский",
                "cities": ("Красноярск", "Норильск", "Ачинск", "Канск"),
            },
            {
                "id": "omsk",
                "title": "Омская область",
                "dadata_region": "Омская",
                "cities": ("Омск",),
            },
            {
                "id": "irkutsk",
                "title": "Иркутская область",
                "dadata_region": "Иркутская",
                "cities": ("Иркутск", "Братск", "Ангарск", "Усть-Илимск"),
            },
            {
                "id": "kemerovo",
                "title": "Кемеровская область",
                "dadata_region": "Кемеровская",
                "cities": ("Кемерово", "Новокузнецк"),
            },
            {
                "id": "tomsk",
                "title": "Томская область",
                "dadata_region": "Томская",
                "cities": ("Томск",),
            },
            {
                "id": "altai",
                "title": "Алтайский край",
                "dadata_region": "Алтайский",
                "cities": ("Барнаул", "Бийск"),
            },
            {
                "id": "altai_rep",
                "title": "Республика Алтай",
                "dadata_region": "Алтай",
                "cities": ("Горно-Алтайск",),
            },
            {
                "id": "khakassia",
                "title": "Хакасия",
                "dadata_region": "Хакасия",
                "cities": ("Абакан",),
            },
            {
                "id": "tyva",
                "title": "Тыва",
                "dadata_region": "Тыва",
                "cities": ("Кызыл",),
            },
            {
                "id": "buryatia",
                "title": "Бурятия",
                "dadata_region": "Бурятия",
                "cities": ("Улан-Удэ",),
            },
            {
                "id": "zabaykal",
                "title": "Забайкальский край",
                "dadata_region": "Забайкальский",
                "cities": ("Чита",),
            },
        ),
    },
    {
        "id": "dfo",
        "title": "Дальневосточный ФО",
        "regions": (
            {
                "id": "primorye",
                "title": "Приморский край",
                "dadata_region": "Приморский",
                "cities": ("Владивосток", "Находка", "Уссурийск", "Артём"),
            },
            {
                "id": "khabarovsk",
                "title": "Хабаровский край",
                "dadata_region": "Хабаровский",
                "cities": ("Хабаровск", "Комсомольск-на-Амуре"),
            },
            {
                "id": "sakha",
                "title": "Якутия",
                "dadata_region": "Саха / Якутия",
                "cities": ("Якутск",),
            },
            {
                "id": "amur",
                "title": "Амурская область",
                "dadata_region": "Амурская",
                "cities": ("Благовещенск",),
            },
            {
                "id": "sakhalin",
                "title": "Сахалинская область",
                "dadata_region": "Сахалинская",
                "cities": ("Южно-Сахалинск",),
            },
            {
                "id": "kamchatka",
                "title": "Камчатский край",
                "dadata_region": "Камчатский",
                "cities": ("Петропавловск-Камчатский",),
            },
            {
                "id": "magadan",
                "title": "Магаданская область",
                "dadata_region": "Магаданская",
                "cities": ("Магадан",),
            },
            {
                "id": "chukotka",
                "title": "Чукотка",
                "dadata_region": "Чукотский",
                "cities": ("Анадырь",),
            },
            {
                "id": "jewish",
                "title": "Еврейская АО",
                "dadata_region": "Еврейская",
                "cities": ("Биробиджан",),
            },
        ),
    },
    {
        "id": "yfo",
        "title": "Южный ФО",
        "regions": (
            {
                "id": "krasnodar",
                "title": "Краснодарский край",
                "dadata_region": "Краснодарский",
                "cities": (
                    "Краснодар",
                    "Сочи",
                    "Новороссийск",
                    "Армавир",
                    "Анапа",
                    "Геленджик",
                ),
            },
            {
                "id": "rostov",
                "title": "Ростовская область",
                "dadata_region": "Ростовская",
                "cities": (
                    "Ростов-на-Дону",
                    "Таганрог",
                    "Шахты",
                    "Новочеркасск",
                    "Волгодонск",
                    "Батайск",
                    "Новошахтинск",
                ),
            },
            {
                "id": "volgograd",
                "title": "Волгоградская область",
                "dadata_region": "Волгоградская",
                "cities": ("Волгоград", "Волжский", "Камышин"),
            },
            {
                "id": "astrakhan",
                "title": "Астраханская область",
                "dadata_region": "Астраханская",
                "cities": ("Астрахань",),
            },
            {
                "id": "adygea",
                "title": "Адыгея",
                "dadata_region": "Адыгея",
                "cities": ("Майкоп",),
            },
            {
                "id": "kalmykia",
                "title": "Калмыкия",
                "dadata_region": "Калмыкия",
                "cities": ("Элиста",),
            },
            {
                "id": "crimea",
                "title": "Крым",
                "dadata_region": "Крым",
                "cities": ("Симферополь", "Керчь", "Ялта", "Евпатория"),
            },
            {
                "id": "sevastopol",
                "title": "Севастополь",
                "dadata_region": "Севастополь",
                "cities": ("Севастополь",),
            },
        ),
    },
    {
        "id": "skfo",
        "title": "Северо-Кавказский ФО",
        "regions": (
            {
                "id": "stavropol",
                "title": "Ставропольский край",
                "dadata_region": "Ставропольский",
                "cities": (
                    "Ставрополь",
                    "Пятигорск",
                    "Кисловодск",
                    "Невинномысск",
                    "Ессентуки",
                    "Минеральные Воды",
                ),
            },
            {
                "id": "dagestan",
                "title": "Дагестан",
                "dadata_region": "Дагестан",
                "cities": ("Махачкала", "Дербент", "Каспийск"),
            },
            {
                "id": "chechnya",
                "title": "Чечня",
                "dadata_region": "Чеченская",
                "cities": ("Грозный",),
            },
            {
                "id": "osetia",
                "title": "Северная Осетия",
                "dadata_region": "Северная Осетия",
                "cities": ("Владикавказ",),
            },
            {
                "id": "kabardino",
                "title": "Кабардино-Балкария",
                "dadata_region": "Кабардино-Балкарская",
                "cities": ("Нальчик",),
            },
        ),
    },
)


def geo_payload() -> dict[str, Any]:
    """Tree + flat searchable index for the web UI."""
    districts = []
    flat: list[dict[str, str]] = []
    seen_cities: set[str] = set()
    for fo in FEDERAL_DISTRICTS:
        regions_out = []
        for reg in fo["regions"]:
            cities = list(reg["cities"])
            regions_out.append(
                {
                    "id": reg["id"],
                    "title": reg["title"],
                    "dadata_region": reg["dadata_region"],
                    "cities": cities,
                }
            )
            flat.append(
                {
                    "kind": "region",
                    "id": reg["id"],
                    "title": reg["title"],
                    "fo": fo["title"],
                    "dadata_region": reg["dadata_region"],
                    "label": f"{reg['title']} · регион · {fo['title']}",
                }
            )
            for city in cities:
                if city in seen_cities:
                    continue
                seen_cities.add(city)
                flat.append(
                    {
                        "kind": "city",
                        "id": city,
                        "title": city,
                        "region_id": reg["id"],
                        "region": reg["title"],
                        "fo": fo["title"],
                        "dadata_region": reg["dadata_region"],
                        "label": f"{city} · {reg['title']}",
                    }
                )
        districts.append({"id": fo["id"], "title": fo["title"], "regions": regions_out})
    flat.sort(key=lambda x: (0 if x["kind"] == "city" else 1, x["title"].lower()))
    return {
        "all_russia": True,
        "districts": districts,
        "flat": flat,
        "cities": [x["title"] for x in flat if x["kind"] == "city"],
    }


def city_list() -> list[str]:
    return list(geo_payload()["cities"])


def parse_geo_selection(
    *,
    city: str = "",
    cities: list[str] | None = None,
    regions: list[str] | None = None,
) -> tuple[list[str], list[str], str]:
    """Normalize UI selection → (cities, dadata_regions, label)."""
    city_out: list[str] = []
    region_out: list[str] = []
    seen_c: set[str] = set()
    seen_r: set[str] = set()

    def add_city(name: str) -> None:
        name = name.strip()
        if not name or name.lower() in {"вся россия", "россия", "all", "*"}:
            return
        key = name.lower()
        if key in seen_c:
            return
        seen_c.add(key)
        city_out.append(name)

    def add_region(name: str) -> None:
        name = name.strip()
        if not name:
            return
        key = name.lower()
        if key in seen_r:
            return
        # Resolve region id or title → dadata_region
        for fo in FEDERAL_DISTRICTS:
            for reg in fo["regions"]:
                if name in {reg["id"], reg["title"], reg["dadata_region"]}:
                    dadata = reg["dadata_region"]
                    if dadata.lower() not in seen_r:
                        seen_r.add(dadata.lower())
                        region_out.append(dadata)
                    return
        if key not in seen_r:
            seen_r.add(key)
            region_out.append(name)

    for item in cities or []:
        add_city(str(item))
    for part in (city or "").replace(";", ",").split(","):
        add_city(part)
    for item in regions or []:
        add_region(str(item))

    if city_out and region_out:
        label = ", ".join(city_out[:4] + ([f"+{len(city_out) - 4}"] if len(city_out) > 4 else []))
        if region_out:
            label += " · " + ", ".join(region_out[:2])
    elif city_out:
        label = ", ".join(city_out[:6])
        if len(city_out) > 6:
            label += f" (+{len(city_out) - 6})"
    elif region_out:
        label = ", ".join(region_out[:6])
        if len(region_out) > 6:
            label += f" (+{len(region_out) - 6})"
    else:
        label = "вся Россия"
    return city_out, region_out, label


def dadata_locations_multi(
    cities: list[str] | None = None,
    regions: list[str] | None = None,
) -> list[dict[str, str]] | None:
    """OR-filter for DaData suggest. None = whole Russia."""
    locs: list[dict[str, str]] = []
    for city in cities or []:
        city = city.strip()
        if city:
            locs.append({"city": city})
    for region in regions or []:
        region = region.strip()
        if region:
            locs.append({"region": region})
    return locs or None


def address_matches_geo(
    address: str,
    cities: list[str] | None = None,
    regions: list[str] | None = None,
) -> bool:
    if not (cities or regions):
        return True
    addr = (address or "").lower()
    for city in cities or []:
        if city.strip().lower() in addr:
            return True
    for region in regions or []:
        if region.strip().lower() in addr:
            return True
    return False
