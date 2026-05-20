from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Session

import os
DB_PATH = os.getenv("DB_PATH", "reports.db")
engine  = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"

    id             = Column(Integer, primary_key=True, index=True)
    type           = Column(String(20))   # "sheriff_sale" | "spot_check"
    created_at     = Column(DateTime, default=datetime.utcnow)
    title          = Column(String(300))
    property_count = Column(Integer, default=0)
    buy_count      = Column(Integer, default=0)
    consider_count = Column(Integer, default=0)
    no_buy_count   = Column(Integer, default=0)
    watch_count    = Column(Integer, default=0)
    perfect_count  = Column(Integer, default=0)
    avoid_count    = Column(Integer, default=0)
    pdf_path       = Column(String(500), nullable=True)
    deals_json     = Column(Text)         # JSON list of analyzed Deal dicts


class PropertyDeal(Base):
    __tablename__ = "property_deals"

    id           = Column(Integer, primary_key=True, index=True)
    sale_id      = Column(String(200), unique=True, index=True, nullable=False)
    source       = Column(String(20),  nullable=False)   # "sheriff_sale" | "spot_check"
    address      = Column(String(500), nullable=False)
    municipality = Column(String(200), nullable=True)
    deal_json    = Column(Text,        nullable=False)
    fingerprint  = Column(String(64),  nullable=True)    # SHA-256(address|min_bid|municipality)
    pdf_hash     = Column(String(64),  nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
