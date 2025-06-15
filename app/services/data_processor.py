import pandas as pd
import pytz
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import StoreStatus, BusinessHours, StoreTimezone
from typing import Dict, List, Tuple
import os

class DataProcessor:
    def __init__(self, db: Session):
        self.db = db
        self._max_timestamp_cache = None
        self._cache_time = None
        self._cache_duration = timedelta(minutes=5)
    
    def get_max_timestamp(self) -> datetime:
        """Dynamically fetch the maximum timestamp from store_status data (synchronous)"""
        # Check cache first
        if (self._max_timestamp_cache and self._cache_time and 
            datetime.utcnow() - self._cache_time < self._cache_duration):
            return self._max_timestamp_cache
        
        # Query for max timestamp (synchronous)
        max_timestamp = self.db.query(func.max(StoreStatus.timestamp_utc)).scalar()
        
        if max_timestamp:
            # Ensure timezone-aware
            if max_timestamp.tzinfo is None:
                max_timestamp = pytz.UTC.localize(max_timestamp)
            
            # Cache the result
            self._max_timestamp_cache = max_timestamp
            self._cache_time = datetime.utcnow()
            return max_timestamp
        else:
            # Fallback if no data exists
            return pytz.UTC.localize(datetime.utcnow())
    
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
        # Ensure all datetime comparisons are timezone-aware
        if start_time.tzinfo is None:
            start_time = pytz.UTC.localize(start_time)
        if end_time.tzinfo is None:
            end_time = pytz.UTC.localize(end_time)
            
        observations = self.db.query(StoreStatus).filter(
            StoreStatus.store_id == store_id,
            StoreStatus.timestamp_utc >= start_time,
            StoreStatus.timestamp_utc <= end_time
        ).order_by(StoreStatus.timestamp_utc).all()
        
        # Ensure all returned timestamps are timezone-aware
        result = []
        for obs in observations:
            timestamp = obs.timestamp_utc
            if timestamp.tzinfo is None:
                timestamp = pytz.UTC.localize(timestamp)
            result.append((timestamp, obs.status))
        
        return result
    
    def calculate_business_hours_overlap(self, start_time: datetime, end_time: datetime, 
                                       business_hours: Dict[int, Tuple[time, time]], 
                                       timezone_str: str) -> List[Tuple[datetime, datetime]]:
        """Calculate overlap between time range and business hours"""
        # Ensure input times are timezone-aware
        if start_time.tzinfo is None:
            start_time = pytz.UTC.localize(start_time)
        if end_time.tzinfo is None:
            end_time = pytz.UTC.localize(end_time)
            
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
                
                # Convert back to UTC - ensure timezone-aware
                day_start_utc = day_start.astimezone(pytz.UTC)
                day_end_utc = day_end.astimezone(pytz.UTC)
                
                # Calculate overlap
                overlap_start = max(current, day_start_utc)
                overlap_end = min(end_time, day_end_utc)
                
                if overlap_start < overlap_end:
                    overlaps.append((overlap_start, overlap_end))
            
            current += timedelta(days=1)
            current = current.replace(hour=0, minute=0, second=0, microsecond=0)
            # Ensure current remains timezone-aware
            if current.tzinfo is None:
                current = pytz.UTC.localize(current)
        
        return overlaps
    
    def interpolate_status(self, observations: List[Tuple[datetime, str]], 
                          business_periods: List[Tuple[datetime, datetime]]) -> Tuple[float, float]:
        """Interpolate uptime/downtime for business periods"""
        total_uptime = 0.0
        total_downtime = 0.0
        
        for period_start, period_end in business_periods:
            # Ensure period times are timezone-aware
            if period_start.tzinfo is None:
                period_start = pytz.UTC.localize(period_start)
            if period_end.tzinfo is None:
                period_end = pytz.UTC.localize(period_end)
                
            period_duration = (period_end - period_start).total_seconds() / 60  # minutes
            
            # Get observations within this period
            period_observations = []
            for ts, status in observations:
                if ts.tzinfo is None:
                    ts = pytz.UTC.localize(ts)
                if period_start <= ts <= period_end:
                    period_observations.append((ts, status))
            
            if not period_observations:
                # No observations, assume last known status or active if none
                if observations:
                    # Find the closest observation before this period
                    closest_obs = None
                    for ts, status in reversed(observations):
                        if ts.tzinfo is None:
                            ts = pytz.UTC.localize(ts)
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
        
        # Ensure all times are timezone-aware
        if period_start.tzinfo is None:
            period_start = pytz.UTC.localize(period_start)
        if period_end.tzinfo is None:
            period_end = pytz.UTC.localize(period_end)
        
        total_uptime = 0.0
        current_time = period_start
        current_status = observations[0][1]  # Start with first observation status
        
        for obs_time, obs_status in observations:
            if obs_time.tzinfo is None:
                obs_time = pytz.UTC.localize(obs_time)
                
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
    
    def calculate_store_metrics(self, store_id: str) -> dict:
        """Calculate uptime/downtime metrics for a store using dynamic max timestamp (synchronous)"""
        # Get dynamic max timestamp (now synchronous)
        max_timestamp = self.get_max_timestamp()
        
        # Calculate time windows based on dynamic max_timestamp
        last_hour_start = max_timestamp - timedelta(hours=1)
        last_day_start = max_timestamp - timedelta(days=1)
        last_week_start = max_timestamp - timedelta(days=7)
        
        # Get store configuration
        timezone_str = self.get_store_timezone(store_id)
        business_hours = self.get_business_hours(store_id)
        
        # Calculate metrics for each period
        metrics = {}
        
        # Last hour
        hour_observations = self.get_store_observations(store_id, last_hour_start, max_timestamp)
        hour_business_periods = self.calculate_business_hours_overlap(
            last_hour_start, max_timestamp, business_hours, timezone_str
        )
        hour_uptime, hour_downtime = self.interpolate_status(hour_observations, hour_business_periods)
        
        # Last day  
        day_observations = self.get_store_observations(store_id, last_day_start, max_timestamp)
        day_business_periods = self.calculate_business_hours_overlap(
            last_day_start, max_timestamp, business_hours, timezone_str
        )
        day_uptime, day_downtime = self.interpolate_status(day_observations, day_business_periods)
        
        # Last week
        week_observations = self.get_store_observations(store_id, last_week_start, max_timestamp)
        week_business_periods = self.calculate_business_hours_overlap(
            last_week_start, max_timestamp, business_hours, timezone_str
        )
        week_uptime, week_downtime = self.interpolate_status(week_observations, week_business_periods)
        
        return {
            "store_id": store_id,
            "uptime_last_hour": round(hour_uptime, 2),
            "downtime_last_hour": round(hour_downtime, 2),
            "uptime_last_day": round(day_uptime / 60, 2),  # Convert to hours
            "downtime_last_day": round(day_downtime / 60, 2),  # Convert to hours
            "uptime_last_week": round(week_uptime / 60, 2),  # Convert to hours
            "downtime_last_week": round(week_downtime / 60, 2),  # Convert to hours
            "report_timestamp": max_timestamp.isoformat()
        }