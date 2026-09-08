from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    id: str
    title: str
    dadata_region: str
    kladr_id: str
    cities: tuple[tuple[str, str], ...]


REGIONS: dict[str, Region] = {
    "tatarstan": Region(
        "tatarstan",
        "Татарстан",
        "Татарстан",
        "16",
        (
            ("kazan", "Казань"),
            ("chelny", "Набережные Челны"),
            ("nizhnekamsk", "Нижнекамск"),
            ("almetyevsk", "Альметьевск"),
        ),
    ),
    "moscow": Region(
        "moscow",
        "Москва",
        "Москва",
        "77",
        (("moscow", "Москва"),),
    ),
    "mosobl": Region(
        "mosobl",
        "Московская обл.",
        "Московская",
        "50",
        (
            ("podolsk", "Подольск"),
            ("khimki", "Химки"),
            ("balashikha", "Балашиха"),
        ),
    ),
    "spb": Region(
        "spb",
        "Санкт-Петербург",
        "Санкт-Петербург",
        "78",
        (("spb", "Санкт-Петербург"),),
    ),
    "bashkiria": Region(
        "bashkiria",
        "Башкортостан",
        "Башкортостан",
        "02",
        (
            ("ufa", "Уфа"),
            ("sterlitamak", "Стерлитамак"),
        ),
    ),
    "krasnodar": Region(
        "krasnodar",
        "Краснодарский край",
        "Краснодарский",
        "23",
        (
            ("krasnodar", "Краснодар"),
            ("sochi", "Сочи"),
        ),
    ),
    "samara": Region(
        "samara",
        "Самарская обл.",
        "Самарская",
        "63",
        (
            ("samara", "Самара"),
            ("togliatti", "Тольятти"),
        ),
    ),
    "nnov": Region(
        "nnov",
        "Нижегородская обл.",
        "Нижегородская",
        "52",
        (("nnov", "Нижний Новгород"),),
    ),
    "sverdlovsk": Region(
        "sverdlovsk",
        "Свердловская обл.",
        "Свердловская",
        "66",
        (("ekb", "Екатеринбург"),),
    ),
    "novosib": Region(
        "novosib",
        "Новосибирская обл.",
        "Новосибирская",
        "54",
        (("novosib", "Новосибирск"),),
    ),
    "rostov": Region(
        "rostov",
        "Ростовская обл.",
        "Ростовская",
        "61",
        (("rostov", "Ростов-на-Дону"),),
    ),
    "chelyabinsk": Region(
        "chelyabinsk",
        "Челябинская обл.",
        "Челябинская",
        "74",
        (("chelyabinsk", "Челябинск"),),
    ),
}


def city_title(region_id: str, city_id: str) -> str:
    region = REGIONS.get(region_id)
    if not region:
        return ""
    for cid, name in region.cities:
        if cid == city_id:
            return name
    return ""


def geo_label(country: str, region: str, city: str) -> str:
    country = country.strip() or "Россия"
    if city.strip():
        return f"{country}, {city.strip()}"
    if region.strip():
        return f"{country}, {region.strip()}"
    return f"{country}, вся страна"


def dadata_locations(
    country: str,
    region: str,
    city: str,
    kladr_id: str = "",
) -> list[dict] | None:
    """Omit locations for all-Russia: country+region together makes DaData ignore the region."""
    city = city.strip()
    region = region.strip()
    kladr_id = (kladr_id or "").strip()
    # Comma-separated multi-city (UI can send "Казань, Самара")
    if "," in city or ";" in city:
        from app.geo_tree import dadata_locations_multi, parse_geo_selection

        cities, regions, _ = parse_geo_selection(city=city, regions=[region] if region else None)
        return dadata_locations_multi(cities, regions)
    if city:
        return [{"city": city}]
    if kladr_id:
        return [{"kladr_id": kladr_id}]
    if region:
        return [{"region": region}]
    return None
