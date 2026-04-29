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


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()
