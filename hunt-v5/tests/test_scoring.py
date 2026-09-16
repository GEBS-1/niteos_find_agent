from app.providers.base import ContactCandidate
from app.services.scoring import score_contact

def test_confirmed_contact():
    c=ContactCandidate('phone','+79990000000','https://example.org','public',True,True,True,True,True)
    assert score_contact(c)==(100,'confirmed')

def test_probable_contact():
    c=ContactCandidate('email','x@example.org','https://example.org','public',True,True,True,False,False)
    assert score_contact(c)==(75,'probable')

def test_unverified_contact():
    c=ContactCandidate('phone','+79990000000','https://example.org','public',True,False,False,False,False)
    assert score_contact(c)==(30,'unverified')
