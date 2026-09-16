import httpx
from app.config import settings
from app.providers.base import CompanyRecord, FounderRecord

class DaDataCompanyProvider:
    URL="https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
    async def by_inn(self,inn):
        if not settings.dadata_api_key: return None
        headers={"Authorization":f"Token {settings.dadata_api_key}","Content-Type":"application/json"}
        async with httpx.AsyncClient(timeout=25) as client:
            r=await client.post(self.URL,headers=headers,json={"query":inn}); r.raise_for_status(); data=r.json()
        suggestions=data.get("suggestions") or []
        if not suggestions: return None
        item=suggestions[0]; d=item.get("data") or {}; mgmt=d.get("management") or {}; finance=d.get("finance") or {}
        founders=[]
        for f in d.get("founders") or []:
            share_obj=f.get("share") or {}; share=share_obj.get("value") if isinstance(share_obj,dict) else None
            founders.append(FounderRecord(kind="company" if "LEGAL" in str(f.get("type") or "").upper() else "person",name=f.get("name") or "",inn=f.get("inn") or "",share_percent=float(share) if share not in (None,"") else None,source="DaData"))
        return CompanyRecord(inn=d.get("inn") or inn,name=((d.get("name") or {}).get("full_with_opf") or item.get("value") or ""),ogrn=d.get("ogrn") or "",legal_address=((d.get("address") or {}).get("unrestricted_value") or ""),status=((d.get("state") or {}).get("status") or ""),revenue=finance.get("revenue"),profit=finance.get("net_profit"),employees=d.get("employee_count"),director_name=mgmt.get("name") or "",founders=founders,source="DaData",source_url="https://dadata.ru/api/find-party/")
