import uuid
import csv
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.database import ReportStatus, StoreStatus
from app.services.data_processor import DataProcessor
from typing import List
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.processor = DataProcessor(db)
        self.reports_dir = "reports"
        os.makedirs(self.reports_dir, exist_ok=True)
    
    def trigger_report(self) -> str:
        """Trigger report generation and return report_id"""
        report_id = str(uuid.uuid4())
        
        # Create report status record
        report_status = ReportStatus(
            report_id=report_id,
            status="Running",
            created_at=datetime.utcnow()
        )
        self.db.add(report_status)
        self.db.commit()
        
        # Start report generation in background
        asyncio.create_task(self._generate_report(report_id))
        
        return report_id
    
    async def _generate_report(self, report_id: str):
        """Generate report asynchronously"""
        try:
            # Get all unique store IDs
            store_ids = self.db.query(StoreStatus.store_id).distinct().all()
            store_ids = [store_id[0] for store_id in store_ids]
            
            report_data = []
            
            # Process stores in parallel
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(self._process_store, store_id)
                    for store_id in store_ids
                ]
                
                for future in futures:
                    result = future.result()
                    if result:
                        report_data.append(result)
            
            # Write CSV file
            file_path = os.path.join(self.reports_dir, f"{report_id}.csv")
            self._write_csv(report_data, file_path)
            
            # Update report status
            self._update_report_status(report_id, "Complete", file_path)
            
        except Exception as e:
            print(f"Error generating report {report_id}: {str(e)}")
            self._update_report_status(report_id, "Failed", None)
    
    def _process_store(self, store_id: str) -> dict:
        """Process a single store and return report data"""
        try:
            max_timestamp = self.processor.max_timestamp
            
            # Calculate time periods
            last_hour = max_timestamp - timedelta(hours=1)
            last_day = max_timestamp - timedelta(days=1)
            last_week = max_timestamp - timedelta(weeks=1)
            
            # Get store data
            timezone_str = self.processor.get_store_timezone(store_id)
            business_hours = self.processor.get_business_hours(store_id)
            
            # Calculate metrics for each period
            metrics = {}
            
            for period_name, start_time in [
                ("hour", last_hour),
                ("day", last_day),
                ("week", last_week)
            ]:
                observations = self.processor.get_store_observations(
                    store_id, start_time, max_timestamp
                )
                
                business_periods = self.processor.calculate_business_hours_overlap(
                    start_time, max_timestamp, business_hours, timezone_str
                )
                
                uptime, downtime = self.processor.interpolate_status(
                    observations, business_periods
                )
                
                # Convert to appropriate units
                if period_name == "hour":
                    metrics[f"uptime_last_{period_name}"] = round(uptime, 2)
                    metrics[f"downtime_last_{period_name}"] = round(downtime, 2)
                else:
                    metrics[f"uptime_last_{period_name}"] = round(uptime / 60, 2)
                    metrics[f"downtime_last_{period_name}"] = round(downtime / 60, 2)
            
            return {
                "store_id": store_id,
                **metrics
            }
            
        except Exception as e:
            print(f"Error processing store {store_id}: {str(e)}")
            return None
    
    def _write_csv(self, report_data: List[dict], file_path: str):
        """Write report data to CSV file"""
        if not report_data:
            return
        
        fieldnames = [
            "store_id", "uptime_last_hour", "uptime_last_day", "uptime_last_week",
            "downtime_last_hour", "downtime_last_day", "downtime_last_week"
        ]
        
        with open(file_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(report_data)
    
    def _update_report_status(self, report_id: str, status: str, file_path: str = None):
        """Update report status in database"""
        report = self.db.query(ReportStatus).filter(
            ReportStatus.report_id == report_id
        ).first()
        
        if report:
            report.status = status
            report.file_path = file_path
            if status == "Complete":
                report.completed_at = datetime.utcnow()
            self.db.commit()
    
    def get_report_status(self, report_id: str) -> dict:
        """Get report status and file if complete"""
        report = self.db.query(ReportStatus).filter(
            ReportStatus.report_id == report_id
        ).first()
        
        if not report:
            return {"status": "Not Found", "report_id": report_id}
        
        return {
            "status": report.status,
            "report_id": report_id,
            "file_path": report.file_path
        }