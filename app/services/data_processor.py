from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.database import StoreStatus, BusinessHours, StoreTimezone
from typing import Dict, List, Tuple
import pytz

class DataProcessor:
    def __init__(self, db: Session):
        self.db = db
        self._max_timestamp_cache = None
        self._cache_time = None
        self._cache_duration = timedelta(minutes=5)  # cache for 5 mins
    
    def get_max_timestamp(self) -> datetime:
        """the latest timestamp from store_status"""
        # check cache for result
        if (self._max_timestamp_cache and self._cache_time and 
            datetime.utcnow() - self._cache_time < self._cache_duration):
            return self._max_timestamp_cache
        
        # query for max timestamp
        max_timestamp = self.db.query(func.max(StoreStatus.timestamp_utc)).scalar()
        
        if max_timestamp:
            # make sure it's timezone aware
            if max_timestamp.tzinfo is None:
                max_timestamp = max_timestamp.replace(tzinfo=pytz.UTC)
            
            # cache it
            self._max_timestamp_cache = max_timestamp
            self._cache_time = datetime.utcnow()
            
            return max_timestamp
        else:
            # fallback if no data
            return datetime.now(pytz.UTC)
    
    def get_store_timezone(self, store_id: str) -> str:
        """timezone for store, default to America/Chicago """
        timezone_record = self.db.query(StoreTimezone).filter(
            StoreTimezone.store_id == store_id
        ).first()
        return timezone_record.timezone_str if timezone_record else "America/Chicago"
    
    def get_business_hours(self, store_id: str) -> Dict[int, Tuple[time, time]]:
        """business hours for store, 24/7 if not found"""
        hours = self.db.query(BusinessHours).filter(
            BusinessHours.store_id == store_id
        ).all()
        
        if not hours:
            # default to 24/7
            return {i: (time(0, 0), time(23, 59, 59)) for i in range(7)}
        
        business_hours = {}
        for hour in hours:
            business_hours[hour.day_of_week] = (hour.start_time_local, hour.end_time_local)
        
        return business_hours
    
    def get_store_observations(self, store_id: str, start_time: datetime, end_time: datetime) -> List[Tuple[datetime, str]]:
        """store status observations within time range"""
        # make sure times are timezone-aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=pytz.UTC)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=pytz.UTC)
            
        observations = self.db.query(StoreStatus).filter(
            StoreStatus.store_id == store_id,
            StoreStatus.timestamp_utc >= start_time,
            StoreStatus.timestamp_utc <= end_time
        ).order_by(StoreStatus.timestamp_utc).all()
        
        # make sure all returned timestamps are timezone-aware
        result = []
        for obs in observations:
            obs_time = obs.timestamp_utc
            if obs_time.tzinfo is None:
                obs_time = obs_time.replace(tzinfo=pytz.UTC)
            result.append((obs_time, obs.status))
        
        return result
    
    def calculate_business_hours_overlap(self, start_time: datetime, end_time: datetime, 
                                       business_hours: Dict[int, Tuple[time, time]], 
                                       timezone_str: str) -> List[Tuple[datetime, datetime]]:
        """overlap between time range and business hours"""
        # ensure input times are timezone-aware
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
                
                # convert business hours to datetime for this day
                day_start = local_time.replace(hour=start_bh.hour, minute=start_bh.minute, 
                                             second=start_bh.second, microsecond=0)
                day_end = local_time.replace(hour=end_bh.hour, minute=end_bh.minute, 
                                           second=end_bh.second, microsecond=0)
                
                # handle overnight business hours
                if end_bh < start_bh:
                    day_end += timedelta(days=1)
                
                # convert back to UTC 
                day_start_utc = day_start.astimezone(pytz.UTC)
                day_end_utc = day_end.astimezone(pytz.UTC)
                
                # calculate overlap
                overlap_start = max(current, day_start_utc)
                overlap_end = min(end_time, day_end_utc)
                
                if overlap_start < overlap_end:
                    overlaps.append((overlap_start, overlap_end))
            
            current += timedelta(days=1)
            current = current.replace(hour=0, minute=0, second=0, microsecond=0)
            if current.tzinfo is None:
                current = pytz.UTC.localize(current)
        
        return overlaps
    
    def interpolate_status(self, observations: List[Tuple[datetime, str]], 
                          business_periods: List[Tuple[datetime, datetime]]) -> Tuple[float, float]:
        """interpolate uptime/downtime for business periods"""
        total_uptime = 0.0
        total_downtime = 0.0
        
        for period_start, period_end in business_periods:
            # Ensure period times are timezone-aware
            if period_start.tzinfo is None:
                period_start = pytz.UTC.localize(period_start)
            if period_end.tzinfo is None:
                period_end = pytz.UTC.localize(period_end)
                
            period_duration = (period_end - period_start).total_seconds() / 60  # minutes
            
            # get observations within this period
            period_observations = []
            for ts, status in observations:
                if ts.tzinfo is None:
                    ts = pytz.UTC.localize(ts)
                if period_start <= ts <= period_end:
                    period_observations.append((ts, status))
            
            if not period_observations:
                # no observations, assume last known status or active if none
                if observations:
                    # find the closest observation before this period
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
                    # no observations at all, assume active
                    total_uptime += period_duration
            else:
                # interpolate based on observations
                period_uptime, period_downtime = self._interpolate_period(
                    period_observations, period_start, period_end
                )
                total_uptime += period_uptime
                total_downtime += period_downtime
        
        return total_uptime, total_downtime
    
    def _interpolate_period(self, observations: List[Tuple[datetime, str]], 
                           period_start: datetime, period_end: datetime) -> Tuple[float, float]:
        """interpolate uptime/downtime for a single business period"""
        if not observations:
            return 0.0, 0.0
        
        # ensure all times are timezone-aware
        if period_start.tzinfo is None:
            period_start = pytz.UTC.localize(period_start)
        if period_end.tzinfo is None:
            period_end = pytz.UTC.localize(period_end)
        
        total_uptime = 0.0
        current_time = period_start
        current_status = observations[0][1]
        
        for obs_time, obs_status in observations:
            if obs_time.tzinfo is None:
                obs_time = pytz.UTC.localize(obs_time)
                
            # add time for current status
            duration = (obs_time - current_time).total_seconds() / 60
            if current_status == 'active':
                total_uptime += duration
            
            current_time = obs_time
            current_status = obs_status
        
        # handle remaining time until period end
        remaining_duration = (period_end - current_time).total_seconds() / 60
        if current_status == 'active':
            total_uptime += remaining_duration
        
        period_duration = (period_end - period_start).total_seconds() / 60
        total_downtime = period_duration - total_uptime
        
        return total_uptime, total_downtime
    
    def calculate_store_metrics(self, store_id: str) -> dict:
        """metrics for a store """
        # get max timestamp
        max_timestamp = self.get_max_timestamp()
        
        # calculate time windows
        last_hour_start = max_timestamp - timedelta(hours=1)
        last_day_start = max_timestamp - timedelta(days=1)
        last_week_start = max_timestamp - timedelta(days=7)
        
        # get observations for each period
        hour_obs = self.get_store_observations(store_id, last_hour_start, max_timestamp)
        day_obs = self.get_store_observations(store_id, last_day_start, max_timestamp)
        week_obs = self.get_store_observations(store_id, last_week_start, max_timestamp)
        
        # count active vs inactive
        def uptime_calculation(observations, total_minutes):
            if not observations:
                return total_minutes, 0  # assume active if no data
            
            active_count = sum(1 for _, status in observations if status == 'active')
            total_count = len(observations)
            
            if total_count == 0:
                return total_minutes, 0
            
            uptime_ratio = active_count / total_count
            uptime = total_minutes * uptime_ratio
            downtime = total_minutes - uptime
            
            return uptime, downtime
        
        # calculate for each period
        hour_up, hour_down = uptime_calculation(hour_obs, 60)
        day_up, day_down = uptime_calculation(day_obs, 24 * 60)
        week_up, week_down = uptime_calculation(week_obs, 7 * 24 * 60)
        
        return {
            "store_id": store_id,
            "uptime_last_hour": round(hour_up, 2),
            "downtime_last_hour": round(hour_down, 2),
            "uptime_last_day": round(day_up / 60, 2),  # convert to hours
            "downtime_last_day": round(day_down / 60, 2),
            "uptime_last_week": round(week_up / 60, 2),
            "downtime_last_week": round(week_down / 60, 2),
            "report_timestamp": max_timestamp.isoformat()
        }
       