from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from app.services.report_service import ReportService
from app.services.data_processor import DataProcessor
from app.models.database import get_db, StoreStatus
import os

router = APIRouter()
report_service = ReportService()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Loop Store Monitoring"}

@router.post("/trigger_report")
async def trigger_report():
    """Trigger report generation"""
    report_id = report_service.trigger_report()
    return {"report_id": report_id}

@router.get("/get_report")
async def get_report(report_id: str):
    """Get report status or download completed report"""
    status = report_service.get_report_status(report_id)
    
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    
    if status["status"] == "Complete":
        filepath = os.path.join("reports", status["filename"])
        if os.path.exists(filepath):
            return FileResponse(
                filepath, 
                media_type="text/csv",
                filename=status["filename"]
            )
        else:
            raise HTTPException(status_code=404, detail="Report file not found")
    
    return status

# Debug endpoints
@router.get("/debug/max_timestamp")
async def get_max_timestamp(db: Session = Depends(get_db)):
    """Get the dynamic maximum timestamp from data"""
    processor = DataProcessor(db)
    max_timestamp = await processor.get_max_timestamp()
    
    return {
        "max_timestamp": max_timestamp.isoformat(),
        "max_timestamp_utc": max_timestamp,
        "cache_time": processor._cache_time.isoformat() if processor._cache_time else None
    }

@router.get("/debug/status_counts")
async def get_status_counts(db: Session = Depends(get_db)):
    """Get count of active/inactive statuses"""
    active_count = db.query(StoreStatus).filter(StoreStatus.status == 'active').count()
    inactive_count = db.query(StoreStatus).filter(StoreStatus.status == 'inactive').count()
    total_count = db.query(StoreStatus).count()
    
    return {
        "active_count": active_count,
        "inactive_count": inactive_count,
        "total_count": total_count
    }

@router.get("/debug/stores_with_downtime")
async def get_stores_with_downtime(db: Session = Depends(get_db)):
    """Get stores that have inactive status (potential downtime)"""
    result = db.execute(text("""
        SELECT store_id, COUNT(*) as inactive_count 
        FROM store_status 
        WHERE status = 'inactive' 
        GROUP BY store_id 
        ORDER BY inactive_count DESC 
        LIMIT 10
    """))
    
    stores = [{"store_id": row[0], "inactive_count": row[1]} for row in result.fetchall()]
    return {"stores_with_downtime": stores}

@router.get("/debug/store/{store_id}")
async def get_store_debug_info(store_id: str, db: Session = Depends(get_db)):
    """Get debug info for a specific store"""
    processor = DataProcessor(db)
    max_timestamp = await processor.get_max_timestamp()
    
    # Get recent observations
    from datetime import timedelta
    recent_start = max_timestamp - timedelta(hours=2)
    observations = processor.get_store_observations(store_id, recent_start, max_timestamp)
    
    # Get store config
    timezone_str = processor.get_store_timezone(store_id)
    business_hours = processor.get_business_hours(store_id)
    
    return {
        "store_id": store_id,
        "max_timestamp": max_timestamp.isoformat(),
        "timezone": timezone_str,
        "business_hours": {str(k): f"{v[0]} - {v[1]}" for k, v in business_hours.items()},
        "recent_observations_count": len(observations),
        "recent_observations": [
            {"timestamp": obs[0].isoformat(), "status": obs[1]} 
            for obs in observations[-5:]  # Last 5 observations
        ]
    }