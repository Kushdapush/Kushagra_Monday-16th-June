# Store Monitoring Service
A FastAPI-based service for monitoring store uptime and generating reports.

## 🚀 Features
- Store uptime/downtime monitoring with minute-level precision
- Business hours aware calculations across different timezones
- Automated report generation with CSV export
- Real-time status tracking and interpolation
- Debug endpoints for system monitoring
- **Timezone-aware** datetime handling

---

## 🛠 Tech Stack
- **FastAPI** (API framework with async support)
- **PostgreSQL** (Database for store data and reports)
- **SQLAlchemy** (ORM with timezone-aware datetime support)
- **Pytz** (Timezone calculations and conversions)
- **Asyncio** (Background report processing)

---

## 🏗️ System Architecture

```
┌───────────────────┐       ┌────────────────────┐       ┌──────────────────┐
│                   │       │                    │       │                  │
│   Store Status    ├──────►│   FastAPI (API)    ├──────►│   PostgreSQL     │
│   Data Sources    │       │   - Report Trigger │       │   - Store Status │
│                   │       │   - Status Check   │       │   - Business Hrs │
└───────────────────┘       └─────────┬──────────┘       │   - Timezones    │
                                      │                  └──────────────────┘
                                      │ Async Tasks
                                      ▼
┌───────────────────┐       ┌────────────────────┐
│                   │       │                    │
│   CSV Reports     │◄──────┤  DataProcessor     │
│   - Uptime/Hour   │       │   - Interpolation  │
│   - Uptime/Day    │       │   - Business Hours │
│   - Uptime/Week   │       │   - Timezone Calc  │
└───────────────────┘       └────────────────────┘
```

---

## 📖 API Documentation
### 🔹 FastAPI Swagger UI
- Access at `http://localhost:8000/docs` when running locally

### 🔹 Endpoints

#### **Report Management**
| Method | Endpoint | Description |
|--------|---------|-------------|
| `POST` | `/api/v1/trigger_report` | Start a new uptime report generation |
| `GET` | `/api/v1/get_report?report_id={id}` | Get report status or download CSV |

#### **Debug & Monitoring**
| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/api/v1/debug/max_timestamp` | Get the latest data timestamp |
| `GET` | `/api/v1/debug/status_counts` | Count of active/inactive statuses |
| `GET` | `/api/v1/debug/stores_with_downtime` | Stores with inactive periods |
| `GET` | `/api/v1/debug/store/{store_id}` | Detailed store information |

#### **Health Check**
| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/health` | System health check |
| `GET` | `/api/v1/health` | Service health status |

---

## 🛠 Local Setup

### 1️⃣ Prerequisites
- **Python 3.11+**
- **PostgreSQL** database
- **Git**

### 2️⃣ Configure Environment
Create a .env file with your database configuration:

```env
DATABASE_URL=postgresql://<username>:<password>@<host>:<port>/<database_name>
```

### 3️⃣ Install Dependencies
```bash
# Clone the repository
git clone <repo-url>
cd name-of-repo

# Create virtual environment
python -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4️⃣ Database Setup
```bash
# Create PostgreSQL database
createdb loop_monitoring
```

### 5️⃣ Load Sample Data
Place your CSV files in the data directory:
- `store_status.csv` - Store status observations
- `menu_hours.csv` - Business hours data
- `timezones.csv` - Store timezone mappings

### 6️⃣ Run the Application
```bash
python app/main.py
```

The API will run on `http://localhost:8000`.

---

## 📡 API Usage Examples

### **1️⃣ Trigger Report Generation**
```bash
curl -X POST "http://localhost:8000/api/v1/trigger_report"
```
**Response:**
```json
{
  "report_id": "1de0a24c-45e5-424b-bac1-2eb5649cdd67"
}
```

### **2️⃣ Check Report Status**
```bash
curl -X GET "http://localhost:8000/api/v1/get_report?report_id=1de0a24c-45e5-424b-bac1-2eb5649cdd67"
```
**Response (Running):**
```json
{
  "status": "Running"
}
```

### **3️⃣ Download Completed Report**
```bash
curl -X GET "http://localhost:8000/api/v1/get_report?report_id=1de0a24c-45e5-424b-bac1-2eb5649cdd67" \
     --output report.csv
```

### **4️⃣ Get Store Debug Information**
```bash
curl -X GET "http://localhost:8000/api/v1/debug/store/1481966498820158979"
```

### **5️⃣ Check System Health**
```bash
curl -X GET "http://localhost:8000/health"
```

---

## 🏗️ Workflow

1. **Data Ingestion**: CSV files are loaded into PostgreSQL with timezone-aware timestamps
2. **Report Trigger**: API endpoint creates a unique report ID and starts background processing
3. **Store Processing**: Each store is analyzed for uptime/downtime across three time periods
4. **Business Hours Calculation**: Only business hours are considered for accurate metrics
5. **Timezone Conversion**: All calculations according to store-specific timezones
6. **Status Interpolation**: Missing data points are correspondingly interpolated
7. **CSV Generation**: Final report is saved to reports directory
8. **Download**: Completed reports are served as downloadable CSV files

---

## 💻 Development

### Database Schema

#### **Store Status Table**
```sql
CREATE TABLE store_status (
    id SERIAL PRIMARY KEY,
    store_id VARCHAR NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    status VARCHAR NOT NULL -- 'active' or 'inactive'
);
```

#### **Business Hours Table**
```sql
CREATE TABLE business_hours (
    id SERIAL PRIMARY KEY,
    store_id VARCHAR NOT NULL,
    day_of_week INTEGER NOT NULL, -- 0=Monday, 6=Sunday
    start_time_local TIME NOT NULL,
    end_time_local TIME NOT NULL
);
```

#### **Store Timezones Table**
```sql
CREATE TABLE store_timezones (
    id SERIAL PRIMARY KEY,
    store_id VARCHAR UNIQUE NOT NULL,
    timezone_str VARCHAR NOT NULL -- e.g., 'America/Chicago'
);
```

#### **Report Status Table**
```sql
CREATE TABLE report_status (
    report_id VARCHAR PRIMARY KEY,
    status VARCHAR DEFAULT 'Running',
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    file_path VARCHAR
);
```

### Key Components

#### **`DataProcessor`**
- Handles all business logic for uptime calculations
- Manages timezone conversions using pytz
- Implements status interpolation algorithms
- Caches maximum timestamp for performance

#### **`ReportService`**
- Manages asynchronous report generation
- Processes stores in batches for memory efficiency
- Handles error recovery and logging
- Generates CSV files with proper formatting

#### **Core Features**
- **Timezone Awareness**: All datetime operations use timezone-aware objects
- **Business Hours Logic**: Calculations respect store-specific operating hours
- **Status Interpolation**: Intelligently fills gaps in status data
- **Batch Processing**: Handles large datasets efficiently
- **Error Handling**: Graceful degradation with detailed logging

### Project Structure
```
Loop-Assignment/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── api/
│   │   └── endpoints.py           # API route definitions
│   ├── models/
│   │   ├── database.py            # SQLAlchemy models and DB setup
│   │   └── schemas.py             # Pydantic request/response models
│   ├── services/
│   │   ├── data_processor.py      # Core business logic
│   │   └── report_service.py      # Report generation service
│   └── utils/                     # Utility functions
├── data/                          # CSV input files
│   ├── store_status.csv
│   ├── menu_hours.csv
│   └── timezones.csv
├── reports/                       # Generated CSV reports
├── requirements.txt               # Python dependencies
├── .env                          # Environment configuration
└── README.md                     # This file
```

---

## ⚙️ Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |

### Application Settings
- **Report Batch Size**: 10 stores per batch for memory efficiency
- **Cache Duration**: 5 minutes for timestamp caching
- **Timezone Handling**: UTC storage with local timezone calculations
- **Default Business Hours**: 24/7 if not specified
- **Default Timezone**: America/Chicago if not specified

---

## 📌 Design Choices & Assumptions

### Key Design Choices
- **PostgreSQL**: Chosen for robust timezone support and complex queries
- **Timezone-Aware Timestamps**: All datetime objects include timezone information
- **Status Interpolation**: Assumes last known status continues until next observation
- **Business Hours Priority**: Only counts time during store operating hours
- **Batch Processing**: Processes stores in groups to manage memory usage

### Assumptions
- **Data Quality**: CSV files are properly formatted and contain valid data
- **Timezone Data**: Store timezone strings are valid pytz timezone identifiers
- **Business Hours**: Missing business hours data defaults to 24/7 operation
- **Status Interpolation**: If no prior status exists, assumes 'active'
- **Report Retention**: Generated reports persist in the filesystem

### Calculation Logic
- **Last Hour**: 60 minutes before max timestamp
- **Last Day**: 24 hours before max timestamp  
- **Last Week**: 7 days before max timestamp
- **Uptime Ratio**: Based on active status observations during business hours
- **Interpolation**: Linear interpolation between known status points

---

## 🧮 Business Hours Overlap & Uptime Calculation Logic

### Overview
Our algorithm calculates uptime/downtime by finding overlaps between time periods and business hours, ensuring we only count operational hours.

### 🔹 How It Works

#### **1. Define Time Periods**
```python
# Calculate periods relative to the latest data timestamp
max_timestamp = get_max_timestamp_utc()
periods = {
    'last_hour': max_timestamp - timedelta(hours=1),
    'last_day': max_timestamp - timedelta(days=1), 
    'last_week': max_timestamp - timedelta(weeks=1)
}
```

#### **2. Status Interpolation**
We fill gaps between status observations by assuming the last known status continues:

```python
# Example: If we have observations at 10:00 AM (active) and 2:00 PM (inactive)
# We assume the store was active from 10:00 AM to 2:00 PM
```

#### **3. Business Hours Segments**
For each day in the analysis period, we create time segments when the store is supposed to be open:

```python
# Example: Store open 9 AM - 5 PM, Monday-Friday
# Creates segments: Mon 9-5, Tue 9-5, Wed 9-5, etc.
# Skips weekends if store is closed
```

#### **4. Calculate Overlaps**
We find where status segments overlap with business hour segments:

```python
def calculate_overlap(status_segment, business_segment):
    start = max(status_segment.start, business_segment.start)
    end = min(status_segment.end, business_segment.end)
    
    if start < end:
        return end - start  # Duration of overlap
    return 0  # No overlap
```

#### **5. Sum Up Results**
- **Uptime**: Sum of all overlaps where status = 'active'
- **Downtime**: Sum of all overlaps where status = 'inactive'

### 🔹 Simple Example

**Store Data:**
- Business Hours: Mon-Fri 9 AM - 5 PM
- Status: Mon 10 AM = Active, Mon 2 PM = Inactive, Mon 4 PM = Active

**Calculation for Monday:**
```
Business Hours: 9 AM ────────────────── 5 PM
Status Timeline: 9AM──10AM──2PM──4PM──5PM
                 ???  ACTIVE  INACTIVE ACTIVE

Result:
- 9-10 AM: Unknown → Assume Active = 1 hour uptime
- 10 AM-2 PM: Active = 4 hours uptime  
- 2-4 PM: Inactive = 2 hours downtime
- 4-5 PM: Active = 1 hour uptime

Total: 6 hours uptime, 2 hours downtime
```

---

## 📊 Sample Report Output

```csv
store_id,uptime_last_hour,downtime_last_hour,uptime_last_day,downtime_last_day,uptime_last_week,downtime_last_week
1481966498820158979,45.0,15.0,18.5,5.5,142.3,25.7
8564726354053924962,60.0,0.0,24.0,0.0,168.0,0.0
```

**Metrics Explanation:**
- **uptime_last_hour/downtime_last_hour**: Minutes of uptime/downtime in the last hour
- **uptime_last_day/downtime_last_day**: Hours of uptime/downtime in the last day
- **uptime_last_week/downtime_last_week**: Hours of uptime/downtime in the last week

---

## 🔍 Monitoring & Debugging

The API includes several debug endpoints to help monitor system health:

- **Timestamp Validation**: Check if data is current and properly loaded
- **Status Distribution**: Verify active vs inactive status ratios
- **Store-Level Analysis**: Deep dive into specific store calculations
- **Downtime Identification**: Quickly identify problematic stores

---

## 🚀 Solution Improvements

### 🔹 Performance Optimizations
- **Database Indexing**: Add indexes on `(store_id, timestamp_utc)` for faster queries
- **Caching**: Cache business hours and timezone data in Redis
- **Batch Processing**: Process multiple stores in parallel
- **Connection Pooling**: Use pgbouncer for better database performance

### 🔹 Data Quality Improvements  
- **Data Validation**: Validate CSV data format and detect anomalies
- **Audit Logging**: Track all data changes and report generations

### 🔹 API Enhancements
- **Multiple Export Formats**: Support JSON, Excel exports
- **Store Filtering**: Filter reports by store region, type, etc.
- **Rate Limiting**: Prevent API abuse

### 🔹 Infrastructure Improvements
- **Containerization**: Add Docker support for easy deployment
- **Health Monitoring**: Add comprehensive health checks
- **Security**: Add authentication and encrypt sensitive data
- **Scalability**: Support horizontal scaling with load balancers

### 🔹 Business Features
- **Alerting**: Send alerts when stores go offline
- **Dashboards**: Real-time monitoring dashboards
- **Scheduled Reports**: Automatic daily/weekly reports
- **Mobile App**: Mobile dashboard for managers

These improvements would make the system more robust, scalable, and suitable for production use in large retail operations.

---