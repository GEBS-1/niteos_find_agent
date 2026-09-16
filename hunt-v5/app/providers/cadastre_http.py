import httpx
from app.config import settings
from app.providers.base import CadastreRecord


def _first_payload(data):
    if isinstance(data, list):
        return data[0] if data else {}
    if not isinstance(data, dict):
        return {}
    for key in ("result", "data", "item", "object"):
        nested = data.get(key)
        if isinstance(nested, list):
            return nested[0] if nested else {}
        if isinstance(nested, dict):
            return nested
    items = data.get("items") or data.get("objects") or data.get("features")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            return first.get("properties") or first
    return data


def _pick(data: dict, *keys):
    for key in keys:
        cur = data
        ok = True
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur.get(part)
        if ok and cur not in (None, ""):
            return cur
    return None


class HttpCadastreProvider:
    # Adapter for a legitimate cadastral/property API.
    # Expected normalized JSON: cadastral_number,address,area,cadastral_value,
    # owner:{type,name,inn,ogrn},source_url,match_confidence
    async def resolve(self,obj):
        if not settings.cadastre_api_url: return None
        headers={}
        if settings.cadastre_api_key: headers["Authorization"]=f"Bearer {settings.cadastre_api_key}"
        async with httpx.AsyncClient(timeout=30) as client:
            r=await client.get(settings.cadastre_api_url,params={"lat":obj.lat,"lon":obj.lon,"address":obj.address,"name":obj.name},headers=headers); r.raise_for_status(); data=r.json()
        data = _first_payload(data)
        if not data:
            return None
        cad = _pick(data, "cadastral_number", "cadastre_number", "cad_num", "cn", "number")
        if not cad:
            return None
        owner = _pick(data, "owner", "right_holder", "rights_holder", "proprietor") or {}
        if not isinstance(owner, dict):
            owner = {"name": owner}
        confidence = _pick(data, "match_confidence", "confidence", "score") or 0
        try:
            confidence = int(float(confidence))
        except (TypeError, ValueError):
            confidence = 0
        return CadastreRecord(
            cadastral_number=str(cad or ""),
            address=str(_pick(data, "address", "readable_address", "location.address") or obj.address or ""),
            area=_pick(data, "area", "build_record_area", "land_record_area"),
            cadastral_value=_pick(data, "cadastral_value", "cadastre_value", "cost_value", "cad_cost"),
            owner_type=str(_pick(owner, "type", "kind") or ""),
            owner_name=str(_pick(owner, "name", "title", "full_name") or ""),
            owner_inn=str(_pick(owner, "inn", "tax_id") or ""),
            owner_ogrn=str(_pick(owner, "ogrn") or ""),
            source="cadastre-http",
            source_url=str(_pick(data, "source_url", "url") or settings.cadastre_api_url),
            match_confidence=confidence,
        )
