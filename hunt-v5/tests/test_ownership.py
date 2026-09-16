import pytest
from app.providers.base import CompanyRecord,FounderRecord
from app.services.ownership import resolve_ultimate_owners

@pytest.mark.asyncio
async def test_recursive_effective_ownership():
    companies={
        'A':CompanyRecord(inn='A',name='A',founders=[FounderRecord('person','Иванов',share_percent=70),FounderRecord('company','B',inn='B',share_percent=30)]),
        'B':CompanyRecord(inn='B',name='B',founders=[FounderRecord('person','Петров',share_percent=80),FounderRecord('person','Сидоров',share_percent=20)])}
    async def fetch(inn): return companies.get(inn)
    owners=await resolve_ultimate_owners('A',fetch); shares={o.full_name:o.effective_share for o in owners}
    assert shares=={'Иванов':70.0,'Петров':24.0,'Сидоров':6.0}

@pytest.mark.asyncio
async def test_cycle_protection():
    companies={'A':CompanyRecord(inn='A',name='A',founders=[FounderRecord('company','B',inn='B',share_percent=100)]),'B':CompanyRecord(inn='B',name='B',founders=[FounderRecord('company','A',inn='A',share_percent=100)])}
    async def fetch(inn): return companies.get(inn)
    assert await resolve_ultimate_owners('A',fetch)==[]
