from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.schemas import ReportResponse, ReportStatusResponse
from app.services.report_service import ReportService
import os

router = APIRouter()

@router.post("/trigger_report", response_model=ReportResponse)
async def trigger_report(db: Session = Depends(get_db)):
    """Trigger report generation"""
    try:
        report_service = ReportService(db)
        report_id = report_service.trigger_report()
        return ReportResponse(report_id=report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_report", response_model=ReportStatusResponse)
async def get_report(report_id: str, db: Session = Depends(get_db)):
    """Get report status or download CSV if complete"""
    try:
        report_service = ReportService(db)
        result = report_service.get_report_status(report_id)
        
        if result["status"] == "Not Found":
            raise HTTPException(status_code=404, detail="Report not found")
        
        if result["status"] == "Complete" and result["file_path"]:
            # Return file download
            if os.path.exists(result["file_path"]):
                return FileResponse(
                    path=result["file_path"],
                    filename=f"report_{report_id}.csv",
                    media_type="text/csv"
                )
            else:
                raise HTTPException(status_code=404, detail="Report file not found")
        
        return ReportStatusResponse(
            status=result["status"],
            report_id=report_id,
            file_path=result.get("file_path")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))