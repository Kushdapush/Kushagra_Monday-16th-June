import pandas as pd
import pytz
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from app.models.database import StoreStatus, BusinessHours, StoreTimezone
from typing import Dict, List, Tuple
import os

class DataProcessor:
    def __init__(self, db: Session):
        self.db = db
        self.max_timestamp = datetime.fromisoformat(os.getenv("MAX_TIMESTAMP"))
    
    def get_store_timezone(self, store_id: str) -> str:
        """Get timezone for store, default to America/Chicago"""
        timezone_record = self.db.query(StoreTimezone).filter(
            StoreTimezone.store_id == store_id
        ).first()
        return timezone_record.timezone_str if timezone_record else "America/Chicago"
    
    def get_business_hours(self, store_id: str) -> Dict[int, Tuple[time, time]]:
        """Get business hours for store, default to 24/7"""
        hours = self.db.query(BusinessHours).filter(
            BusinessHours.store_id == store_id
        ).all()
        
        if not hours:
            # Default to 24/7
            return {i: (time(0, 0), time(23, 59, 59)) for i in range(7)}
        
        business_hours = {}
        for hour in hours:
            business_hours[hour.day_of_week] = (hour.start_time_local, hour.end_time_local)
        
        return business_hours
    
    def get_store_observations(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Tuple[datetime, str]]:
        """Get store status observations within time range"""
        observations = self.db.query(StoreStatus).filter(
            StoreStatus.store_id == store_id,
            StoreStatus.timestamp_utc >= start_time,
            StoreStatus.timestamp_utc <= end_time
        ).order_by(StoreStatus.timestamp_utc).all()
        
        return [(obs.timestamp_utc, obs.status) for obs in observations]
    
    def calculate_business_hours_overlap(self, start_time: datetime, end_time: datetime, 
                                       business_hours: Dict[int, Tuple[time, time]], 
                                       timezone_str: str) -> List[Tuple[datetime, datetime]]:
        """Calculate overlap between time range and business hours"""
        tz = pytz.timezone(timezone_str)
        overlaps = []
        
        current = start_time
        while current < end_time:
            local_time = current.astimezone(tz)
            day_of_week = local_time.weekday()
            
            if day_of_week in business_hours:
                start_bh, end_bh = business_hours[day_of_week]
                
                # Convert business hours to datetime for this day
                day_start = local_time.replace(hour=start_bh.hour, minute=start_bh.minute, 
                                             second=start_bh.second, microsecond=0)
                day_end = local_time.replace(hour=end_bh.hour, minute=end_bh.minute, 
                                           second=end_bh.second, microsecond=0)
                
                # Handle overnight business hours
                if end_bh < start_bh:
                    day_end += timedelta(days=1)
                
                # Convert back to UTC
                day_start_utc = day_start.astimezone(pytz.UTC)
                day_end_utc = day_end.astimezone(pytz.UTC)
                
                # Calculate overlap
                overlap_start = max(current, day_start_utc)
                overlap_end = min(end_time, day_end_utc)
                
                if overlap_start < overlap_end:
                    overlaps.append((overlap_start, overlap_end))
            
            current += timedelta(days=1)
            current = current.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return overlaps
    
    def interpolate_status(self, observations: List[Tuple[datetime, str]], 
                          business_periods: List[Tuple[datetime, datetime]]) -> Tuple[float, float]:
        """Interpolate uptime/downtime for business periods"""
        total_uptime = 0.0
        total_downtime = 0.0
        
        for period_start, period_end in business_periods:
            period_duration = (period_end - period_start).total_seconds() / 60  # minutes
            
            # Get observations within this period
            period_observations = [
                (ts, status) for ts, status in observations
                if period_start <= ts <= period_end
            ]
            
            if not period_observations:
                # No observations, assume last known status or active if none
                if observations:
                    # Find the closest observation before this period
                    closest_obs = None
                    for ts, status in reversed(observations):
                        if ts < period_start:
                            closest_obs = status
                            break
                    
                    if closest_obs == 'active':
                        total_uptime += period_duration
                    else:
                        total_downtime += period_duration
                else:
                    # No observations at all, assume active
                    total_uptime += period_duration
            else:
                # Interpolate based on observations
                period_uptime, period_downtime = self._interpolate_period(
                    period_observations, period_start, period_end
                )
                total_uptime += period_uptime
                total_downtime += period_downtime
        
        return total_uptime, total_downtime
    
    def _interpolate_period(self, observations: List[Tuple[datetime, str]], 
                           period_start: datetime, period_end: datetime) -> Tuple[float, float]:
        """Interpolate uptime/downtime for a single business period"""
        if not observations:
            return 0.0, 0.0
        
        total_uptime = 0.0
        current_time = period_start
        current_status = observations[0][1]  # Start with first observation status
        
        for obs_time, obs_status in observations:
            # Add time for current status
            duration = (obs_time - current_time).total_seconds() / 60
            if current_status == 'active':
                total_uptime += duration
            
            current_time = obs_time
            current_status = obs_status
        
        # Handle remaining time until period end
        remaining_duration = (period_end - current_time).total_seconds() / 60
        if current_status == 'active':
            total_uptime += remaining_duration
        
        period_duration = (period_end - period_start).total_seconds() / 60
        total_downtime = period_duration - total_uptime
        
        return total_uptime, total_downtime