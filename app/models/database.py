from sqlalchemy import create_engine, Column, String, DateTime, Integer, Time, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class StoreStatus(Base):
    __tablename__ = "store_status"
    
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(String, index=True)
    timestamp_utc = Column(DateTime)
    status = Column(String)  # 'active' or 'inactive'

class BusinessHours(Base):
    __tablename__ = "business_hours"
    
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(String, index=True)
    day_of_week = Column(Integer)  # 0=Monday, 6=Sunday
    start_time_local = Column(Time)
    end_time_local = Column(Time)

class StoreTimezone(Base):
    __tablename__ = "store_timezones"
    
    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(String, index=True, unique=True)
    timezone_str = Column(String)

class ReportStatus(Base):
    __tablename__ = "report_status"
    
    report_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="Running")  # 'Running', 'Complete', 'Failed'
    created_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
    file_path = Column(String, nullable=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()