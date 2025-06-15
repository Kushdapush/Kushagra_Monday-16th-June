import asyncio
import uuid
import csv
import os
from app.services.data_processor import DataProcessor
from app.models.database import SessionLocal
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

class ReportService:
    def __init__(self, db=None):
        self.db = db
        self.reports = {}
        self.max_workers = 10  
    
    def trigger_report(self) -> str:
        """Trigger a new report generation"""
        report_id = str(uuid.uuid4())
        self.reports[report_id] = {"status": "Running"}
        
        asyncio.create_task(self._generate_report(report_id))
        return report_id
    
    def get_report_status(self, report_id: str) -> dict:
        """Get report status"""
        if report_id not in self.reports:
            return {"status": "Not Found"}
        return self.reports[report_id]
    
    async def _generate_report(self, report_id: str):
        """Generate the actual report"""
        try:
            logger.info(f"Starting report generation for {report_id}")
            
            db = SessionLocal()
            try:
                result = db.execute(text("SELECT DISTINCT store_id FROM store_status"))
                store_ids = [row[0] for row in result.fetchall()]
                
                logger.info(f"Processing {len(store_ids)} stores")
                
                all_metrics = []
                processor = DataProcessor(db)
                
                max_timestamp = processor.get_max_timestamp()
                logger.info(f"Using max timestamp: {max_timestamp}")
                
                batch_size = 10
                for i in range(0, len(store_ids), batch_size):
                    batch = store_ids[i:i + batch_size]
                    batch_metrics = []
                    
                    for store_id in batch:
                        try:
                            metrics = processor.calculate_store_metrics(store_id)
                            batch_metrics.append(metrics)
                        except Exception as e:
                            logger.error(f"Error processing store {store_id}: {e}")
                            batch_metrics.append({
                                "store_id": store_id,
                                "uptime_last_hour": 0,
                                "downtime_last_hour": 0,
                                "uptime_last_day": 0,
                                "downtime_last_day": 0,
                                "uptime_last_week": 0,
                                "downtime_last_week": 0,
                                "report_timestamp": max_timestamp.isoformat(),
                                "error": str(e)
                            })
                    
                    all_metrics.extend(batch_metrics)
                    logger.info(f"Processed batch {i//batch_size + 1}/{(len(store_ids)-1)//batch_size + 1}")
                
                filename = f"{report_id}.csv"
                filepath = os.path.join("reports", filename)
                
                os.makedirs("reports", exist_ok=True)
                
                with open(filepath, 'w', newline='') as csvfile:
                    fieldnames = [
                        'store_id', 'uptime_last_hour', 'downtime_last_hour',
                        'uptime_last_day', 'downtime_last_day', 
                        'uptime_last_week', 'downtime_last_week'
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for metrics in all_metrics:
                        csv_row = {k: v for k, v in metrics.items() if k in fieldnames}
                        writer.writerow(csv_row)
                
                self.reports[report_id] = {
                    "status": "Complete",
                    "filename": filename,
                    "total_stores": len(all_metrics)
                }
                
                logger.info(f"Report {report_id} completed successfully")
                
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"Report generation failed for {report_id}: {e}")
            self.reports[report_id] = {
                "status": "Failed", 
                "error": str(e)
            }