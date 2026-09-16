from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class Hunt(Base):
    __tablename__ = "hunts"
    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(300))
    requested_count: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(50), default="created")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    results = relationship("HuntResult", back_populates="hunt", cascade="all, delete-orphan")

class ObjectEntity(Base):
    __tablename__ = "objects"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(500))
    address: Mapped[str] = mapped_column(String(700), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    category: Mapped[str] = mapped_column(String(200), default="")
    photo_url: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_provider: Mapped[str] = mapped_column(String(100), default="")
    cadastral_number: Mapped[str] = mapped_column(String(100), default="")
    cadastral_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadastral_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadastre_status: Mapped[str] = mapped_column(String(50), default="not_checked")
    cadastre_source: Mapped[str] = mapped_column(Text, default="")

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    inn: Mapped[str] = mapped_column(String(20), unique=True)
    ogrn: Mapped[str] = mapped_column(String(30), default="")
    name: Mapped[str] = mapped_column(String(500))
    legal_address: Mapped[str] = mapped_column(String(700), default="")
    status: Mapped[str] = mapped_column(String(100), default="")
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, default="")

class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(250), default="")
    company_inn: Mapped[str] = mapped_column(String(20), default="")
    direct_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(Text, default="")

class OwnershipEdge(Base):
    __tablename__ = "ownership_edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_company_inn: Mapped[str] = mapped_column(String(20))
    to_kind: Mapped[str] = mapped_column(String(30))
    to_name: Mapped[str] = mapped_column(String(500))
    to_company_inn: Mapped[str] = mapped_column(String(20), default="")
    share_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(Text, default="")

class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    company_inn: Mapped[str] = mapped_column(String(20), default="")
    contact_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(700))
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(100), default="")
    is_direct_person_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    name_match: Mapped[bool] = mapped_column(Boolean, default=False)
    company_match: Mapped[bool] = mapped_column(Boolean, default=False)
    role_match: Mapped[bool] = mapped_column(Boolean, default=False)
    city_match: Mapped[bool] = mapped_column(Boolean, default=False)
    explicit_person_link: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="unverified")

class HuntResult(Base):
    __tablename__ = "hunt_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    hunt_id: Mapped[int] = mapped_column(ForeignKey("hunts.id"))
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id"))
    owner_company_inn: Mapped[str] = mapped_column(String(20), default="")
    relation_status: Mapped[str] = mapped_column(String(50), default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    hunt = relationship("Hunt", back_populates="results")
