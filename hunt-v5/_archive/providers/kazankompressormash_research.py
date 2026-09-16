from __future__ import annotations

from app.services.person_osint import PersonSignal, resolve_person_contacts

PHOTO_URL = "https://stcdn.business-online.ru/v2/25-08-20/74698/bophotos-318059-1-kopiya.jpg"
PHOTO_SOURCE = "https://www.business-gazeta.ru/article/680750"
OFFICIAL = "https://compressormash.ru/"
OFFICIAL_CONTACT = "https://compressormash.ru/contact/"
OFFICIAL_MANAGEMENT = "https://compressormash.ru/about/management/"
COMPANY_REGISTRY = "https://companies.rbc.ru/id/1021603620114-pao-kazanskij-zavod-kompressornogo-mashinostroeniya/"
MANAGER_DIRECTORY = "https://kazan.dk.ru/wiki/sagdiev-ilnur"
CHIEF_ENGINEER_CURRENT = "https://trt-tv.ru/2024/10/11/v-kazanskij-gospital-veteranov-vojn-peredali-mediczinskoe-oborudovanie-dlya-reabilitaczii-paczientov-uchastnikov-svo/"
CHIEF_ENGINEER_SECONDARY = "https://www.so-ups.ru/odu-volga/news/odu-volga-news-view/news/21379/"
GROUP_TRANSITION = "https://www.business-gazeta.ru/article/680750"
CADASTRE_REFERENCE = "https://base.garant.ru/39334007/"
NALIVAIKO_SOURCE = "https://www.aktt.org/images/studentu/trud/vakan/Srednegodovaya_potrebnost_v_kadrakh.pdf"


def card() -> dict:
    sagdiev_contacts = resolve_person_contacts([
        PersonSignal(
            full_name="Сагдиев Ильнур Ильдарович",
            company="АО «Казанькомпрессормаш»",
            role="Управляющий директор",
            city="Казань",
            contact_type="phone",
            value="+7 (843) 291-79-21",
            source_url=MANAGER_DIRECTORY,
            source_type="public_business_person_directory",
            published_for_person=True,
            current_role_match=True,
            company_match=True,
            city_match=True,
        ),
    ])

    return {
        "research_mode": "real_public_sources",
        "object": {
            "name": "АО «Казанькомпрессормаш» — главный административный фасад",
            "address": "420029, Республика Татарстан, Казань, ул. Халитова, 1",
            "coordinates": {"lat": 55.8197728, "lon": 49.1860954, "confidence": 70},
            "map_url": "https://yandex.ru/maps/?ll=49.186095%2C55.819773&z=17&l=map%2Cstv",
            "photo": {
                "url": PHOTO_URL,
                "source_url": PHOTO_SOURCE,
                "source_type": "news_photo",
                "status": "confirmed_visual",
                "note": "На фото читается вывеска «КАЗАНЬКОМПРЕССОРМАШ»; подходит как фронтальный визуал для предварительной концепции подсветки.",
            },
            "visual_fit": {
                "score": 92,
                "features": [
                    "краснокирпичный исторический/индустриальный фасад",
                    "выраженная центральная входная группа",
                    "карниз и зелёная кровля",
                    "ритм окон, пригодный для акцентного света",
                    "крупная фирменная вывеска на кровле/фасаде",
                ],
            },
            "cadastre": {
                "status": "requires_provider_resolution",
                "exact_facade_cadastral_number": None,
                "why": "В открытом веб-поиске не найден надёжный кадастровый номер именно фасадного здания по адресу Халитова, 1. Соседний промышленный комплекс по Халитова, 8 имеет подтверждённые кадастровые объекты, но код не переносит их на Халитова, 1.",
                "reference_source": CADASTRE_REFERENCE,
            },
        },
        "operator_company": {
            "name": "АО «Казанский завод компрессорного машиностроения» (АО «Казанькомпрессормаш»)",
            "inn": "1660004878",
            "ogrn": "1021603620114",
            "kpp": "166001001",
            "status": "active",
            "legal_address": "Республика Татарстан, г. Казань, ул. Халитова, д. 1",
            "official_site": OFFICIAL,
            "company_phone": ["+7 (843) 291-79-79", "+7 (843) 291-78-78", "+7 (843) 567-38-90"],
            "company_email": "info@hms-kkm.ru",
            "source_urls": [OFFICIAL_CONTACT, COMPANY_REGISTRY],
        },
        "control_and_ownership": {
            "management_organization": "ООО «УК «Группа ГМС»",
            "management_organization_status": "registry-supported",
            "shareholder_chain_status": "transition_or_not_fully_public",
            "note": "В 2025 публично сообщалось о разрешении РусГазДобыче приобрести ключевые активы Группы ГМС; это не используется как доказательство прямого владения конкретным зданием или как готовая цепочка конечного физлица без реестрового подтверждения.",
            "source_urls": [GROUP_TRANSITION],
        },
        "decision_makers": [
            {
                "full_name": "Бакиров Альберт Асхатович",
                "role": "заместитель управляющего директора по техническому развитию — главный инженер",
                "role_status": "confirmed_recent_public",
                "role_priority": 100,
                "contacts": [],
                "contact_status": "direct_public_contact_not_found",
                "sources": [CHIEF_ENGINEER_CURRENT, CHIEF_ENGINEER_SECONDARY],
                "why_relevant": "Первый технический ЛПР для архитектурного/инженерного решения по объекту.",
            },
            {
                "full_name": "Сагдиев Ильнур Ильдарович",
                "role": "управляющий директор",
                "role_status": "confirmed_current_official",
                "role_priority": 75,
                "contacts": sagdiev_contacts,
                "sources": [OFFICIAL_MANAGEMENT, MANAGER_DIRECTORY],
                "why_relevant": "Руководитель предприятия; использовать как резервный или эскалационный контакт.",
            },
            {
                "full_name": "Наливайко Игорь Михайлович",
                "role": "главный металлург",
                "role_status": "public_industry_document",
                "role_priority": 72,
                "contacts": [
                    {
                        "contact_type": "phone",
                        "value": "+7 (843) 291-78-78, доб. 32-48",
                        "source_url": NALIVAIKO_SOURCE,
                        "source_type": "public_industry_document",
                        "confidence": 100,
                        "status": "confirmed",
                        "historical": False,
                        "reason": "ФИО, должность, предприятие, телефон и email опубликованы одной строкой в отраслевом документе",
                    },
                    {
                        "contact_type": "email",
                        "value": "Igor.Nalivajko@hms-kkm.ru",
                        "source_url": NALIVAIKO_SOURCE,
                        "source_type": "public_industry_document",
                        "confidence": 100,
                        "status": "confirmed",
                        "historical": False,
                        "reason": "ФИО, должность, предприятие, телефон и email опубликованы одной строкой в отраслевом документе",
                    },
                ],
                "sources": [NALIVAIKO_SOURCE],
                "why_relevant": "Подтверждённый персональный рабочий контакт внутри технического контура предприятия.",
            },
            {
                "full_name": "Владислав Ермолаев",
                "role": "главный инженер проекта",
                "role_status": "public_professional_profile",
                "role_priority": 82,
                "contacts": [{
                    "contact_type": "professional_profile",
                    "value": "Сетка — профиль, доступно действие «написать»",
                    "source_url": "https://setka.ru/users/0199d50a-8e66-71b0-bcdf-822d6dc0321d",
                    "source_type": "professional_network",
                    "confidence": 80,
                    "status": "probable",
                    "historical": False,
                    "reason": "профиль прямо указывает Казанькомпрессормаш и должность",
                }],
                "sources": ["https://setka.ru/users/0199d50a-8e66-71b0-bcdf-822d6dc0321d"],
                "why_relevant": "Может быть входом в инженерный контур, но не равнозначен главному инженеру предприятия.",
            },
        ],
        "recommended_route": {
            "primary": "Бакиров Альберт Асхатович",
            "secondary": "Владислав Ермолаев",
            "escalation": "Сагдиев Ильнур Ильдарович",
            "reason": "Подсветка затрагивает фасад, электрику и эксплуатацию; технический контур релевантнее общего руководства.",
        },
        "proposal": {
            "status": "draft_from_verified_facts",
            "text": (
                "Предлагаем сделать для главного фасада Казанькомпрессормаша предварительную концепцию архитектурной подсветки: "
                "подчеркнуть краснокирпичную пластику здания, центральную входную группу, ритм окон и фирменную вывеску, "
                "не превращая промышленный объект в декоративный фасад. Первый этап — 2–3 визуальных сценария по существующему фото, "
                "после интереса — светотехнический расчёт, подбор оборудования и оценка бюджета."
            ),
        },
        "verification": {
            "overall": 86,
            "checks": {
                "real_building_and_address": True,
                "front_facade_photo": True,
                "company_requisites": True,
                "current_managing_director": True,
                "chief_engineer_identified": True,
                "direct_person_contact_managing_director": True,
                "direct_person_contact_chief_engineer": False,
                "exact_facade_cadastre": False,
                "building_owner_from_egrn": False,
            },
            "honest_gap": "До 100% не хватает EGRN/кадастрового провайдера для точного здания Халитова, 1 и подтверждённого прямого контакта главного инженера.",
        },
    }
