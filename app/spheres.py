from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SphereOption:
    id: str
    label: str
    query: str


@dataclass(frozen=True)
class Sphere:
    id: str
    title: str
    okved: tuple[str, ...]
    options: tuple[SphereOption, ...]
    idea: str

    @property
    def queries(self) -> tuple[str, ...]:
        return tuple(o.query for o in self.options)


SPHERES: dict[str, Sphere] = {
    "shops": Sphere(
        id="shops",
        title="Магазины / пятёрочки",
        okved=("47.11", "47.19", "47.25"),
        options=(
            SphereOption("shop", "Любой продуктовый", "магазин"),
            SphereOption("pyaterochka", "Пятёрочка", "пятёрочка"),
            SphereOption("magnit", "Магнит", "магнит"),
            SphereOption("produktovy", "Продуктовый", "продуктовый магазин"),
        ),
        idea="Ритейл: зал + крыльцо, линейка NT-park / панели, не промышленный пролёт",
    ),
    "laundry": Sphere(
        id="laundry",
        title="Прачечные",
        okved=("96.01",),
        options=(
            SphereOption("laundry", "Прачечная", "прачечная"),
            SphereOption("dry", "Химчистка", "химчистка"),
        ),
        idea="Влажный цех: IP65, линейный промышленный, не бытовая люстра",
    ),
    "warehouse": Sphere(
        id="warehouse",
        title="Склады",
        okved=("52.10", "52.29"),
        options=(
            SphereOption("sklad", "Склад", "склад"),
            SphereOption("logistika", "Логистика", "логистика"),
            SphereOption("terminal", "Терминал", "терминал"),
        ),
        idea="Пролёт: NT-TOP / промышленный IP65, двор NT-WAY",
    ),
    "commercial": Sphere(
        id="commercial",
        title="Коммерческие здания",
        okved=("68.20", "68.32", "41.20", "55.10", "56.10", "47.19"),
        options=(
            SphereOption("mall", "ТЦ / ТРК", "торговый центр"),
            SphereOption("business", "Бизнес-центр", "бизнес центр"),
            SphereOption("hotel", "Отель", "гостиница"),
            SphereOption("restaurant", "Ресторанный комплекс", "ресторанный комплекс"),
            SphereOption("facade", "Фасад под подсветку", "коммерческое здание фасад"),
        ),
        idea=(
            "Архитектурная подсветка: фасад, входная группа, вывеска, периметр, "
            "акцентные линии и сценарии вечернего вида"
        ),
    ),
    "azs": Sphere(
        id="azs",
        title="АЗС",
        okved=("47.30",),
        options=(
            SphereOption("azs", "АЗС", "АЗС"),
            SphereOption("zapravka", "Заправка", "автозаправка"),
        ),
        idea="Ex: NT-WAY навес, NT-PROM ULTRA Ex, NT-LIRA",
    ),
    "industry": Sphere(
        id="industry",
        title="Промка / цеха",
        okved=("10.11", "10.89", "25.11", "25.99", "28.29", "28.41"),
        options=(
            SphereOption("zavod", "Завод", "завод"),
            SphereOption("ceh", "Цех", "цех"),
            SphereOption("proizv", "Производство", "производство"),
            SphereOption("promzdanie", "Промздание", "промышленное здание"),
        ),
        idea="NT-PROM / NT-ЛУЧ, пыль и высота пролёта",
    ),
    "sports": Sphere(
        id="sports",
        title="Спорт / стадионы",
        okved=("93.11", "93.13", "93.29", "96.04"),
        options=(
            SphereOption("stadium", "Стадион", "стадион"),
            SphereOption("arena", "Арена", "арена"),
            SphereOption("complex", "Спорткомплекс", "спортивный комплекс"),
            SphereOption("fitness", "Фитнес", "фитнес центр"),
            SphereOption("pool", "Бассейн", "бассейн"),
        ),
        idea="Спорт: зал, трибуны, площадка — высокий свет, равномерность, IP для улицы",
    ),
    "street": Sphere(
        id="street",
        title="Улица / двор / парковка",
        okved=("52.21", "68.20", "81.10", "81.29"),
        options=(
            SphereOption("parking", "Парковка", "парковка"),
            SphereOption("yard", "Двор ЖК", "дворовое освещение"),
            SphereOption("street", "Улица", "уличное освещение"),
            SphereOption("road", "Дорога / развязка", "освещение дороги"),
        ),
        idea="Улица и двор: NT-WAY, опоры, парковка, периметр территории",
    ),
    "housing": Sphere(
        id="housing",
        title="ЖКХ / жилые комплексы",
        okved=("68.32", "68.20", "41.20", "81.10"),
        options=(
            SphereOption("jk", "Жилой комплекс", "жилой комплекс"),
            SphereOption("uk", "Управляющая компания", "управляющая компания ЖКХ"),
            SphereOption("tszh", "ТСЖ / ТСН", "ТСЖ"),
            SphereOption("entrance", "Подъезд / двор", "освещение двора ЖКХ"),
        ),
        idea="ЖКХ: двор, подъезды, фасад дома, входные группы",
    ),
    "social": Sphere(
        id="social",
        title="Школы / больницы / культура",
        okved=("85.13", "85.14", "86.10", "90.04", "91.02"),
        options=(
            SphereOption("school", "Школа", "школа"),
            SphereOption("lyceum", "Лицей", "лицей"),
            SphereOption("gymnasium", "Гимназия", "гимназия"),
            SphereOption("hospital", "Больница", "больница"),
            SphereOption("clinic", "Поликлиника", "поликлиника"),
            SphereOption("museum", "Музей / ДК", "дворец культуры"),
        ),
        idea="Соцобъекты: комфортный свет в залах, фасад, территория",
    ),
    "office": Sphere(
        id="office",
        title="Офисы / деловые центры",
        okved=("68.20", "68.32", "62.01", "70.22", "82.11"),
        options=(
            SphereOption("bc", "Бизнес-центр", "бизнес центр"),
            SphereOption("office", "Офисное здание", "офисное здание"),
            SphereOption("cowork", "Коворкинг", "коворкинг"),
            SphereOption("hq", "Штаб-квартира", "офис компании"),
        ),
        idea="Офис: open-space, переговорки, фасад и входная группа",
    ),
}


def parse_okved(raw: str) -> list[str]:
    parts = []
    for chunk in raw.replace(";", ",").split(","):
        code = chunk.strip()
        if code:
            parts.append(code)
    return parts
