from pydantic import BaseModel
from datetime import datetime, time
from typing import Optional

class StoreStatusCreate(BaseModel):
    store_id: str
    timestamp_utc: datetime
    status: str

class BusinessHoursCreate(BaseModel):
    store_id: str
    day_of_week: int
    start_time_local: time
    end_time_local: time

class StoreTimezoneCreate(BaseModel):
    store_id: str
    timezone_str: str

class ReportResponse(BaseModel):
    report_id: str

class ReportStatusResponse(BaseModel):
    status: str
    report_id: str
    file_path: Optional[str] = None

class StoreReport(BaseModel):
    store_id: str
    uptime_last_hour: float
    uptime_last_day: float
    uptime_last_week: float
    downtime_last_hour: float
    downtime_last_day: float
    downtime_last_week: float