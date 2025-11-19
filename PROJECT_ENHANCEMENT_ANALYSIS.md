# Building Monitor - Project Enhancement Analysis

**Date:** November 19, 2025
**Status:** Deprecated/Unmaintained - Rapid Development MVP
**Purpose:** Comprehensive enhancement roadmap for production-grade refactoring

---

## Executive Summary

The **Building Monitor** is a functional NYC real estate monitoring application that tracks building violations and 311 complaints, delivering Discord notifications for property changes. Built rapidly as an MVP with speed prioritized over polish, the application successfully achieves its core objective but requires significant architectural, security, and code quality improvements to become a maintainable, production-grade system.

**Current State:**
- ✅ Core functionality works (monitoring, scraping, notifications)
- ✅ Basic web UI for management
- ✅ Docker containerization with CI/CD pipeline
- ❌ Security vulnerabilities (hardcoded credentials, exposed API keys)
- ❌ No testing infrastructure
- ❌ Monolithic architecture with poor separation of concerns
- ❌ Unused/dead code (~40% of utils directory)
- ❌ Limited error handling and observability

**Recommendation:** This project needs a structured refactoring initiative organized into three phases: **Critical Fixes** (security & stability), **Architectural Refactoring** (maintainability), and **Feature Enhancement** (polish & capabilities).

---

## Table of Contents

1. [Current Architecture Overview](#current-architecture-overview)
2. [Critical Issues (Priority: Immediate)](#critical-issues-priority-immediate)
3. [Code Quality Issues (Priority: High)](#code-quality-issues-priority-high)
4. [Architectural Improvements (Priority: High)](#architectural-improvements-priority-high)
5. [Feature Enhancements (Priority: Medium)](#feature-enhancements-priority-medium)
6. [DevOps & Operational Improvements](#devops--operational-improvements)
7. [Proposed Architecture Refactoring](#proposed-architecture-refactoring)
8. [Implementation Roadmap](#implementation-roadmap)

---

## Current Architecture Overview

### Technology Stack
- **Language:** Python 3.11
- **Web Framework:** Streamlit (UI)
- **Database:** SQLite3 (file-based)
- **Deployment:** Docker + Docker Compose
- **CI/CD:** GitHub Actions → Docker Hub
- **Target Platform:** Unraid

### Core Components

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI (ui.py)                 │
│              Dashboard | Insights | Management          │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│          Building Monitor (building_monitor.py)         │
│   Scheduler | BIS Scraper | 311 API | Notifications    │
└───────────────────┬────────────────────┬────────────────┘
                    │                    │
         ┌──────────▼──────┐    ┌───────▼────────┐
         │  SQLite3 DB     │    │  Discord API   │
         │  (violations,   │    │  (webhooks)    │
         │   complaints,   │    └────────────────┘
         │   owners)       │
         └─────────────────┘
                    │
         ┌──────────▼──────────────┐
         │  External Data Sources  │
         │  • NYC BIS (scraping)   │
         │  • NYC 311 API          │
         └─────────────────────────┘
```

### Database Schema

```sql
owners
├── id (INTEGER PRIMARY KEY)
├── name (TEXT NOT NULL)
├── email (TEXT)
├── phone (TEXT)
├── discord_webhook (TEXT)
└── schedule (TEXT)  -- JSON array

address_owners (many-to-many)
├── address (TEXT)
└── owner_id (INTEGER)

bis_status
├── address (TEXT)
├── bin (TEXT)
├── last_checked (TIMESTAMP)
├── dob_violations (INTEGER)
├── ecb_violations (INTEGER)
└── owner_id (INTEGER)

complaints_311
├── incident_id (TEXT PRIMARY KEY)
├── address (TEXT)
├── created_date (TEXT)
├── closed_date (TEXT)
├── status (TEXT)
├── complaint_type (TEXT)
├── descriptor (TEXT)
└── owner_id (INTEGER)
```

### File Structure Analysis

```
building-monitor/
├── src/
│   ├── building_monitor.py   (920 lines) - Core monitoring logic ⚠️ Monolithic
│   └── ui.py                 (808 lines) - Streamlit UI ⚠️ Mixed concerns
├── utils/                               ⚠️ Mostly unused
│   ├── zillow_api.py         🔴 HARDCODED API KEY
│   ├── sheets_export.py      ⚠️ Unused
│   ├── nyc_open_data.py      ⚠️ Unused
│   ├── location_helpers.py   ⚠️ Unused
│   └── snapshot_store.py     ⚠️ Unused
├── docker/
│   ├── Dockerfile            ✅ Multi-arch build
│   └── docker-compose.yml    ⚠️ Healthcheck broken
├── config/                   🔴 Contains secrets (gitignored)
│   ├── addresses.txt
│   ├── webhook.txt           🔴 Plaintext Discord webhooks
│   ├── schedule.json
│   └── proxy.txt             🔴 Proxy credentials
├── dbs/
│   └── building_monitor.db
└── .github/workflows/
    └── docker-build.yml      ✅ Automated CI/CD
```

---

## Critical Issues (Priority: Immediate)

### 🔴 1. Security Vulnerabilities

#### A. Hardcoded Credentials & API Keys

**Location:** `/utils/zillow_api.py:5, 9, 17`
```python
# CRITICAL: API key hardcoded in source code
ZILLOW_API_KEY = "X1-ZWz1..." # Exposed in version control
```

**Location:** `/src/ui.py:34`
```python
# Hardcoded Oxylabs proxy credentials
return "http://customer-kappy_nrNdL-cc-US:3tGCOHQaFsfv1pzlrDAm+@pr.oxylabs.io:7777"
```

**Impact:**
- API keys visible in GitHub repository (public or private)
- Proxy credentials exposed (potential financial impact)
- Compromised keys require rotation and code changes

**Remediation:**
```python
# Use environment variables
import os
ZILLOW_API_KEY = os.getenv("ZILLOW_API_KEY")
PROXY_URL = os.getenv("PROXY_URL")

# Or use python-dotenv
from dotenv import load_dotenv
load_dotenv()
```

#### B. No Authentication on Web UI

**Issue:** Streamlit UI (port 8501) is publicly accessible without authentication

**Impact:**
- Anyone can view monitored addresses
- Unauthorized users can trigger checks, modify addresses, view owner data
- Potential for abuse (spam checks, data scraping)

**Remediation Options:**
1. **Streamlit-authenticator** (quick fix)
   ```python
   import streamlit_authenticator as stauth
   ```
2. **Reverse proxy with HTTP Basic Auth** (nginx)
3. **OAuth 2.0 integration** (production-grade)
4. **VPN/Network-level restriction** (Unraid-specific)

#### C. Plaintext Secret Storage

**Issue:** Secrets stored in plaintext files (webhook.txt, proxy.txt)

**Remediation:**
- Use encrypted storage (Vault, AWS Secrets Manager)
- Minimum: Use environment variables
- Consider: Docker secrets or encrypted configs

### 🔴 2. Critical Bugs & Stability Issues

#### A. Docker Healthcheck Failure

**Location:** `/docker/docker-compose.yml`
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8501"]
```

**Issue:** `curl` is not installed in `python:3.11-slim` image

**Fix:**
```dockerfile
# Option 1: Install curl
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Option 2: Use Python for healthcheck
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501')"]

# Option 3: Use wget (usually available)
test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8501/_stcore/health"]
```

#### B. Database Schema Migration Fragility

**Location:** `/src/building_monitor.py:298-310`
```python
# Schema changes via try/catch - fragile and error-prone
try:
    cursor.execute("ALTER TABLE bis_status ADD COLUMN owner_id INTEGER")
    conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists
```

**Issues:**
- No migration versioning
- Silent failures mask real errors
- No rollback mechanism
- Cannot recreate database from scratch reliably

**Remediation:**
- Use **Alembic** for migrations
- Version-controlled migration scripts
- Proper up/down migrations

#### C. No Log Rotation

**Location:** `/src/building_monitor.py:64`
```python
file_handler = logging.FileHandler(LOG_FILE)  # No rotation
```

**Impact:**
- Log file grows unbounded
- Disk space exhaustion possible
- Performance degradation

**Fix:**
```python
from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

---

## Code Quality Issues (Priority: High)

### 1. Dead Code & Unused Modules

**Analysis:**
- **5 utility modules** in `/utils/` appear unused in main application
- ~40% of codebase is potentially dead code
- Increases maintenance burden and confusion

**Files to Review/Remove:**
```
utils/zillow_api.py        - No imports found in main code (HAS API KEY!)
utils/sheets_export.py     - Google Sheets integration (unused)
utils/nyc_open_data.py     - Crime data & permits (unused)
utils/location_helpers.py  - Geographic helpers (unused)
utils/snapshot_store.py    - SQLite snapshot class (unused)
```

**Action:**
1. Verify with grep search for imports
2. Remove or move to `/archive/` directory
3. **CRITICAL:** Remove zillow_api.py after extracting any needed functionality

### 2. Monolithic Files & Poor Separation of Concerns

**Issues:**

**A. building_monitor.py (920 lines)**
- Combines: scheduling, scraping, API calls, database access, notifications, logging config
- Violates Single Responsibility Principle
- Difficult to test individual components

**B. ui.py (808 lines)**
- Mixes: UI rendering, business logic (BIN scraping), database queries, file I/O
- UI framework tightly coupled to data access
- Cannot reuse logic outside Streamlit

**Proposed Refactoring:**
```
src/
├── core/
│   ├── scheduler.py          # Schedule management
│   ├── scrapers/
│   │   ├── bis_scraper.py    # BIS website scraping
│   │   └── nyc311_client.py  # 311 API client
│   ├── notifications/
│   │   ├── discord.py        # Discord webhook sender
│   │   ├── email.py          # Email notifications (future)
│   │   └── sms.py            # SMS notifications (future)
│   └── models.py             # Data models/entities
├── data/
│   ├── database.py           # Database connection manager
│   ├── repositories/
│   │   ├── address_repo.py
│   │   ├── owner_repo.py
│   │   ├── violation_repo.py
│   │   └── complaint_repo.py
│   └── migrations/           # Alembic migrations
├── services/
│   ├── monitoring_service.py # Orchestrates checking
│   ├── address_service.py    # Address operations
│   └── owner_service.py      # Owner management
├── ui/
│   ├── app.py                # Streamlit entry point
│   └── pages/                # Multi-page Streamlit app
│       ├── dashboard.py
│       ├── insights.py
│       ├── addresses.py
│       ├── owners.py
│       └── settings.py
├── config/
│   ├── settings.py           # Centralized config (pydantic)
│   └── logging_config.py     # Logging setup
└── utils/
    ├── address_parser.py     # Address parsing utilities
    └── retry.py              # Retry decorators
```

### 3. Insufficient Error Handling

**Examples:**

**A. API calls without proper error handling**
```python
# From building_monitor.py - 311 API call
response = requests.get(url, params=params, timeout=30)
complaints = response.json()  # What if response is not JSON?
```

**B. No retry with exponential backoff**
```python
# From building_monitor.py:483
for attempt in range(2):  # Simple retry, no backoff
    try:
        response = requests.get(...)
        break
    except Exception:
        if attempt < 1:
            time.sleep(2)  # Fixed delay
```

**Remediation:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    reraise=True
)
def fetch_bis_data(address, proxies=None):
    response = requests.get(url, proxies=proxies, timeout=30)
    response.raise_for_status()
    return response.text
```

### 4. No Testing Infrastructure

**Current State:**
- ❌ No unit tests
- ❌ No integration tests
- ❌ No test fixtures
- ❌ No CI test pipeline
- ❌ No test coverage measurement

**Impact:**
- Refactoring is risky (no safety net)
- Regressions go undetected
- Difficult to validate behavior changes
- New contributors have no test examples

**Minimum Test Coverage Needed:**
```python
tests/
├── unit/
│   ├── test_address_parser.py      # Address parsing logic
│   ├── test_bis_scraper.py         # HTML parsing (mock responses)
│   ├── test_notifications.py       # Discord webhook formatting
│   └── test_repositories.py        # Database operations (in-memory SQLite)
├── integration/
│   ├── test_monitoring_service.py  # End-to-end check flow
│   └── test_api_clients.py         # Real API calls (mocked/recorded)
├── fixtures/
│   ├── sample_bis_response.html
│   ├── sample_311_response.json
│   └── test_database.sql
└── conftest.py                     # Pytest configuration
```

**Recommended Tools:**
- **pytest** - Test framework
- **pytest-cov** - Coverage measurement
- **responses** or **vcrpy** - Mock HTTP requests
- **freezegun** - Mock datetime for scheduler tests

### 5. Inconsistent Configuration Management

**Issues:**

**A. Multiple requirements.txt files**
```
/requirements.txt          # Root level (unused?)
/src/requirements.txt      # Actually used by Dockerfile
```

**B. Mixed configuration approaches**
- File-based: addresses.txt, webhook.txt, schedule.json, proxy.txt
- Hardcoded: Default proxy in ui.py, schedule times
- Database: Owner-specific webhooks/schedules (unused)

**C. No environment-specific configs**
- No distinction between dev/staging/prod
- Cannot easily run tests with different settings

**Proposed Solution:**
```python
# config/settings.py using Pydantic
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./dbs/building_monitor.db"

    # External APIs
    nyc_311_api_key: str | None = None
    zillow_api_key: str | None = None

    # Proxy
    proxy_url: str | None = None

    # Notifications
    discord_webhook: str | None = None

    # Scheduler
    schedule_times: list[int] = [8, 12, 20]
    timezone: str = "America/New_York"

    # Logging
    log_level: str = "INFO"
    log_file: str = "./dbs/building_monitor.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Usage
settings = Settings()  # Automatically loads from .env
```

---

## Architectural Improvements (Priority: High)

### 1. Implement Clean Architecture / Layered Architecture

**Current Problem:** Direct dependencies between UI, business logic, and data access

**Proposed Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│              Presentation Layer (UI)                    │
│         Streamlit UI | Future: REST API                 │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│              Service Layer (Business Logic)             │
│    MonitoringService | AddressService | OwnerService    │
│           (Orchestrates use cases)                      │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│            Repository Layer (Data Access)               │
│  AddressRepo | ViolationRepo | ComplaintRepo | OwnerRepo│
│         (Abstracts database operations)                 │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│              Infrastructure Layer                       │
│   Database | External APIs (BIS, 311) | Notifications   │
└─────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ Testable (mock repositories in service tests)
- ✅ Maintainable (changes isolated to layers)
- ✅ Reusable (services can be called from API or CLI)
- ✅ Clear dependencies (layers only depend downward)

### 2. Add API Layer (FastAPI)

**Motivation:**
- Enable programmatic access (not just UI)
- Allow webhooks/integrations from other systems
- Mobile app potential
- Better separation from Streamlit (which is UI-focused)

**Proposed Endpoints:**
```
GET    /api/v1/addresses               # List monitored addresses
POST   /api/v1/addresses               # Add address
DELETE /api/v1/addresses/{id}          # Remove address
GET    /api/v1/addresses/{id}/status   # Get current violations/complaints

GET    /api/v1/owners                  # List owners
POST   /api/v1/owners                  # Create owner
PUT    /api/v1/owners/{id}             # Update owner
GET    /api/v1/owners/{id}/addresses   # Get owner's addresses

POST   /api/v1/checks                  # Trigger manual check
GET    /api/v1/checks/{id}/status      # Get check status

GET    /api/v1/health                  # Health check endpoint
GET    /api/v1/metrics                 # Prometheus metrics
```

**FastAPI Implementation Sketch:**
```python
# src/api/main.py
from fastapi import FastAPI, Depends
from src.services.monitoring_service import MonitoringService
from src.services.address_service import AddressService

app = FastAPI(title="Building Monitor API", version="1.0.0")

@app.post("/api/v1/checks")
async def trigger_check(
    address: str,
    monitoring_service: MonitoringService = Depends()
):
    result = await monitoring_service.check_address(address)
    return {"status": "completed", "result": result}

@app.get("/api/v1/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}
```

### 3. Database Improvements

#### A. Add Proper Indexing
```sql
-- Current: No explicit indexes (only PRIMARY KEY)
-- Proposed:
CREATE INDEX idx_bis_status_address ON bis_status(address);
CREATE INDEX idx_bis_status_owner_id ON bis_status(owner_id);
CREATE INDEX idx_complaints_address ON complaints_311(address);
CREATE INDEX idx_complaints_owner_id ON complaints_311(owner_id);
CREATE INDEX idx_complaints_status ON complaints_311(status);
CREATE INDEX idx_address_owners_owner_id ON address_owners(owner_id);
```

#### B. Add Timestamps & Audit Fields
```sql
ALTER TABLE owners ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE owners ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

#### C. Consider PostgreSQL Migration
**Current:** SQLite (file-based, single-writer)

**Limitations:**
- No concurrent writes (UI + scheduler conflicts possible)
- Limited analytics capabilities
- No connection pooling
- Not suitable for multi-instance deployments

**When to Migrate:**
- Multiple users editing simultaneously
- Analytics/reporting workload increases
- Scaling to multiple containers
- Need for replication/backups

**PostgreSQL Benefits:**
- ACID transactions with MVCC (multi-version concurrency control)
- Full-text search built-in
- JSON column types (for flexible owner preferences)
- TimescaleDB extension (time-series data for historical analysis)

### 4. Introduce Caching Layer

**Use Cases:**
1. **BIN Lookups** - BINs rarely change, cache for 30 days
2. **311 API Responses** - Cache for 1 hour (NYC updates periodically)
3. **Address Parsing** - Cache parsed addresses by raw string

**Implementation Options:**

**Option 1: Redis (Production)**
```python
import redis
from functools import wraps

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

def cached(ttl=3600):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            cached_value = redis_client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)

            result = func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

@cached(ttl=2592000)  # 30 days
def scrape_bin_for_address(address):
    # Expensive BIS scraping
    ...
```

**Option 2: In-Memory (Development)**
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def parse_address_for_bis(address):
    # Fast in-process cache
    ...
```

---

## Feature Enhancements (Priority: Medium)

### 1. Implement Missing Notification Channels

**Currently:** Only Discord webhooks supported

**Stored but Not Implemented:**
- Email addresses (owners.email)
- Phone numbers (owners.phone)
- Per-owner schedules (owners.schedule)

**Enhancement 1A: Email Notifications**

**Recommended Service:** SendGrid, AWS SES, or Mailgun

```python
# src/core/notifications/email.py
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

class EmailNotifier:
    def __init__(self, api_key: str, from_email: str):
        self.client = SendGridAPIClient(api_key)
        self.from_email = from_email

    def send_violation_alert(self, to_email: str, changes: list):
        message = Mail(
            from_email=self.from_email,
            to_emails=to_email,
            subject=f"Building Monitor: {len(changes)} changes detected",
            html_content=self._render_email_template(changes)
        )
        response = self.client.send(message)
        return response.status_code == 202
```

**Enhancement 1B: SMS Notifications**

**Recommended Service:** Twilio

```python
# src/core/notifications/sms.py
from twilio.rest import Client

class SMSNotifier:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    def send_alert(self, to_number: str, message: str):
        self.client.messages.create(
            body=message,
            from_=self.from_number,
            to=to_number
        )
```

**Enhancement 1C: Unified Notification Service**

```python
# src/services/notification_service.py
class NotificationService:
    def __init__(self):
        self.discord = DiscordNotifier()
        self.email = EmailNotifier()
        self.sms = SMSNotifier()

    def notify_owner(self, owner: Owner, changes: list):
        """Send notifications via all configured channels for owner."""
        results = {}

        if owner.discord_webhook:
            results['discord'] = self.discord.send(owner.discord_webhook, changes)

        if owner.email:
            results['email'] = self.email.send_violation_alert(owner.email, changes)

        if owner.phone:
            # Only send SMS for high-priority changes
            if self._is_high_priority(changes):
                results['sms'] = self.sms.send_alert(owner.phone,
                    f"ALERT: {len(changes)} critical building changes detected"
                )

        return results
```

### 2. Advanced Scheduling & Per-Owner Preferences

**Current:** Global schedule for all addresses (8am, 12pm, 8pm)

**Stored but Unused:** `owners.schedule` column (JSON)

**Enhancement:**
```python
# Support per-owner schedules
{
    "owner_id": 1,
    "schedule": {
        "times": [9, 17],  # 9am, 5pm only
        "days": ["mon", "tue", "wed", "thu", "fri"],  # Weekdays only
        "timezone": "America/Los_Angeles"
    }
}

# Implementation in scheduler
def should_check_for_owner(owner: Owner, current_time: datetime) -> bool:
    """Determine if we should check this owner's addresses now."""
    schedule = json.loads(owner.schedule) if owner.schedule else DEFAULT_SCHEDULE

    # Check day of week
    if schedule.get("days"):
        day_name = current_time.strftime("%a").lower()
        if day_name not in schedule["days"]:
            return False

    # Check time
    hour = current_time.hour
    if hour not in schedule["times"]:
        return False

    return True
```

### 3. Historical Trend Analysis & Reporting

**Current:** Only stores latest status, no historical trending

**Enhancement: Violation History Tracking**
```sql
CREATE TABLE violation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL,
    bin TEXT,
    snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dob_violations INTEGER,
    ecb_violations INTEGER,
    dob_open_violations INTEGER,
    ecb_open_violations INTEGER
);

-- Enable trend queries
SELECT
    address,
    snapshot_date,
    dob_violations,
    dob_violations - LAG(dob_violations) OVER (
        PARTITION BY address ORDER BY snapshot_date
    ) as violation_change
FROM violation_history
WHERE address = '123 Main St'
ORDER BY snapshot_date DESC;
```

**UI Enhancement: Trend Charts**
```python
# In Streamlit UI
import plotly.graph_objects as go

def show_violation_trends(address: str):
    history = get_violation_history(address)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history['snapshot_date'],
        y=history['dob_violations'],
        name='DOB Violations',
        line=dict(color='red')
    ))

    st.plotly_chart(fig)
```

### 4. Smart Alerting & Filtering

**Current:** Notifies on any change (noisy)

**Enhancement: Configurable Alert Rules**
```python
# Per-owner alert preferences
alert_preferences = {
    "min_violation_increase": 5,      # Only alert if violations increase by 5+
    "complaint_types": [               # Only these complaint types
        "HEAT/HOT WATER",
        "ILLEGAL CONVERSION",
        "ELEVATOR"
    ],
    "quiet_hours": {
        "start": 22,  # 10pm
        "end": 8      # 8am
    },
    "digest_mode": "daily",  # "immediate", "daily", "weekly"
}

def should_alert(owner: Owner, changes: list) -> bool:
    prefs = owner.alert_preferences

    # Filter by complaint type
    filtered_changes = [
        c for c in changes
        if c.get('complaint_type') in prefs['complaint_types']
    ]

    # Check violation threshold
    violation_increase = sum(c.get('violation_change', 0) for c in changes)
    if violation_increase < prefs['min_violation_increase']:
        return False

    return len(filtered_changes) > 0
```

### 5. Export & Reporting Features

**Enhancement 5A: PDF Reports**
```python
# Generate monthly violation summary PDFs
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def generate_monthly_report(owner_id: int, month: str):
    addresses = get_owner_addresses(owner_id)
    violations = get_violations_for_month(addresses, month)

    pdf = canvas.Canvas(f"reports/{owner_id}_{month}.pdf", pagesize=letter)
    # ... render report
    pdf.save()
```

**Enhancement 5B: CSV Exports**
```python
# Already has sheets_export.py but unused
# Enhance to export all data
def export_to_csv(owner_id: int):
    import pandas as pd

    addresses = get_owner_addresses(owner_id)
    violations = get_all_violations(addresses)
    complaints = get_all_complaints(addresses)

    df_violations = pd.DataFrame(violations)
    df_complaints = pd.DataFrame(complaints)

    df_violations.to_csv(f"exports/violations_{owner_id}.csv", index=False)
    df_complaints.to_csv(f"exports/complaints_{owner_id}.csv", index=False)
```

### 6. Advanced NYC Data Integration

**Unused Utilities Ready to Integrate:**
- `/utils/nyc_open_data.py` - Crime data & DOB permits

**Potential Enhancements:**
```python
# Integrate permit data
def get_construction_permits(address: str):
    """Show active construction permits - indicates future changes."""
    permits = fetch_dob_permits(address)
    return [p for p in permits if p['status'] == 'APPROVED']

# Integrate crime data
def get_neighborhood_crime_stats(address: str):
    """Provide context on area safety trends."""
    lat, lon = geocode_address(address)
    crimes = fetch_crimes_near_location(lat, lon, radius_miles=0.5)
    return aggregate_by_type(crimes)
```

---

## DevOps & Operational Improvements

### 1. Proper Secrets Management

**Current State:**
- Hardcoded credentials in code
- Plaintext files (webhook.txt, proxy.txt)
- No secret rotation

**Enhancement Options:**

**Option A: Environment Variables (Minimum)**
```yaml
# docker-compose.yml
services:
  building-monitor:
    environment:
      - ZILLOW_API_KEY=${ZILLOW_API_KEY}
      - PROXY_URL=${PROXY_URL}
      - DISCORD_WEBHOOK=${DISCORD_WEBHOOK}
    env_file:
      - .env  # Gitignored
```

**Option B: Docker Secrets (Better)**
```yaml
# docker-compose.yml
services:
  building-monitor:
    secrets:
      - zillow_api_key
      - proxy_credentials
      - discord_webhook

secrets:
  zillow_api_key:
    file: ./secrets/zillow_api_key.txt
  proxy_credentials:
    file: ./secrets/proxy.txt
  discord_webhook:
    file: ./secrets/webhook.txt
```

**Option C: HashiCorp Vault (Production)**
```python
import hvac

def get_secret(path: str, key: str):
    client = hvac.Client(url=os.getenv('VAULT_ADDR'))
    client.token = os.getenv('VAULT_TOKEN')
    secret = client.secrets.kv.v2.read_secret_version(path=path)
    return secret['data']['data'][key]

ZILLOW_API_KEY = get_secret('building-monitor', 'zillow_api_key')
```

### 2. Observability & Monitoring

**Current State:**
- Basic file logging
- No metrics collection
- No alerting on application errors
- No performance monitoring

**Enhancement 2A: Structured Logging**
```python
import structlog

logger = structlog.get_logger()

# Rich contextual logging
logger.info(
    "violation_check_completed",
    address="123 Main St",
    dob_violations=10,
    ecb_violations=2,
    duration_ms=1250,
    proxy_used=True
)

# Machine-parseable JSON output for log aggregation
```

**Enhancement 2B: Prometheus Metrics**
```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
checks_total = Counter('building_monitor_checks_total', 'Total checks performed', ['address', 'status'])
check_duration = Histogram('building_monitor_check_duration_seconds', 'Check duration', ['address'])
current_violations = Gauge('building_monitor_violations', 'Current violation count', ['address', 'type'])

# Instrument code
with check_duration.labels(address=address).time():
    violations = get_bis_summary(address)
    checks_total.labels(address=address, status='success').inc()
    current_violations.labels(address=address, type='dob').set(violations['dob'])
```

**Enhancement 2C: Health Check Endpoint**
```python
@app.get("/health")
def health_check():
    checks = {
        "database": check_database_connection(),
        "bis_api": check_bis_accessibility(),
        "311_api": check_311_api(),
        "disk_space": check_disk_space()
    }

    healthy = all(checks.values())
    status_code = 200 if healthy else 503

    return JSONResponse(
        content={"status": "healthy" if healthy else "degraded", "checks": checks},
        status_code=status_code
    )
```

**Enhancement 2D: Error Tracking (Sentry)**
```python
import sentry_sdk

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("ENVIRONMENT", "production"),
    traces_sample_rate=0.1
)

# Automatic error reporting with context
try:
    violations = scrape_bis_website(address)
except Exception as e:
    sentry_sdk.capture_exception(e)
    logger.error("bis_scrape_failed", address=address, error=str(e))
```

### 3. Improved Docker Configuration

**Enhancement 3A: Multi-Stage Builds**
```dockerfile
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
COPY src/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime image (smaller)
FROM python:3.11-slim
WORKDIR /app

# Install only curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy only installed packages
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application
COPY src/ ./src/

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["streamlit", "run", "src/ui.py"]
```

**Enhancement 3B: Docker Compose with Dependencies**
```yaml
version: '3.8'

services:
  building-monitor:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8501:8501"
    volumes:
      - ./config:/app/config
      - ./dbs:/app/dbs
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/building_monitor
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=building_monitor
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

### 4. CI/CD Enhancements

**Current:** Basic Docker build & push to Docker Hub

**Enhancement 4A: Add Testing Stage**
```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r src/requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: pytest --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run ruff
        uses: chartboost/ruff-action@v1

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'

  build:
    needs: [test, lint, security-scan]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    # ... existing Docker build
```

**Enhancement 4B: Semantic Versioning**
```yaml
# Use semantic versioning instead of just "latest"
- name: Docker meta
  id: meta
  uses: docker/metadata-action@v4
  with:
    images: kappy1928/building-monitor
    tags: |
      type=semver,pattern={{version}}
      type=semver,pattern={{major}}.{{minor}}
      type=sha,prefix={{branch}}-
      type=raw,value=latest,enable={{is_default_branch}}
```

### 5. Backup & Disaster Recovery

**Current:** No backup strategy

**Enhancement:**
```bash
#!/bin/bash
# backup.sh - Run as cron job

BACKUP_DIR="/backups/building-monitor"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup SQLite database
sqlite3 /app/dbs/building_monitor.db ".backup '${BACKUP_DIR}/db_backup_${DATE}.db'"

# Backup config files
tar -czf ${BACKUP_DIR}/config_${DATE}.tar.gz /app/config/

# Keep only last 30 days of backups
find ${BACKUP_DIR} -name "*.db" -mtime +30 -delete
find ${BACKUP_DIR} -name "*.tar.gz" -mtime +30 -delete

# Upload to S3 (optional)
aws s3 sync ${BACKUP_DIR} s3://my-bucket/building-monitor-backups/
```

---

## Proposed Architecture Refactoring

### Phase 1: Extract Core Components

**Goal:** Separate concerns without breaking existing functionality

```
Step 1: Extract data models
├── Create src/models/address.py
├── Create src/models/owner.py
├── Create src/models/violation.py
└── Create src/models/complaint.py

Step 2: Extract repositories
├── Create src/data/repositories/base.py (abstract base)
├── Create src/data/repositories/address_repository.py
├── Create src/data/repositories/owner_repository.py
└── Create src/data/repositories/violation_repository.py

Step 3: Extract external clients
├── Create src/core/scrapers/bis_scraper.py
├── Create src/core/scrapers/nyc311_client.py
└── Create src/core/scrapers/base.py (interface)

Step 4: Extract notification handlers
├── Create src/core/notifications/base.py (interface)
├── Create src/core/notifications/discord.py
└── Create src/core/notifications/notification_service.py
```

**Example: Address Repository**
```python
# src/data/repositories/address_repository.py
from typing import List, Optional
from src.models.address import Address
from src.data.database import get_db_connection

class AddressRepository:
    def get_all(self) -> List[Address]:
        """Get all monitored addresses."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT address, bin FROM bis_status")
            rows = cursor.fetchall()
            return [Address(address=r[0], bin=r[1]) for r in rows]

    def get_by_address(self, address: str) -> Optional[Address]:
        """Get specific address by string."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT address, bin, last_checked FROM bis_status WHERE LOWER(address) = LOWER(?)",
                (address,)
            )
            row = cursor.fetchone()
            if row:
                return Address(address=row[0], bin=row[1], last_checked=row[2])
            return None

    def save(self, address: Address) -> None:
        """Save or update address."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bis_status (address, bin, last_checked, dob_violations, ecb_violations)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    bin = excluded.bin,
                    last_checked = excluded.last_checked,
                    dob_violations = excluded.dob_violations,
                    ecb_violations = excluded.ecb_violations
            """, (address.address, address.bin, address.last_checked,
                  address.dob_violations, address.ecb_violations))
            conn.commit()
```

### Phase 2: Introduce Service Layer

**Goal:** Encapsulate business logic, coordinate between repositories and external clients

```python
# src/services/monitoring_service.py
from src.data.repositories.address_repository import AddressRepository
from src.data.repositories.violation_repository import ViolationRepository
from src.core.scrapers.bis_scraper import BISScraper
from src.core.scrapers.nyc311_client import NYC311Client
from src.core.notifications.notification_service import NotificationService

class MonitoringService:
    def __init__(
        self,
        address_repo: AddressRepository,
        violation_repo: ViolationRepository,
        bis_scraper: BISScraper,
        nyc311_client: NYC311Client,
        notification_service: NotificationService
    ):
        self.address_repo = address_repo
        self.violation_repo = violation_repo
        self.bis_scraper = bis_scraper
        self.nyc311_client = nyc311_client
        self.notification_service = notification_service

    def check_address(self, address: str) -> dict:
        """
        Check a single address for violations and complaints.
        Returns detected changes.
        """
        # Get current state
        current_violations = self.violation_repo.get_latest(address)

        # Fetch fresh data
        bis_data = self.bis_scraper.get_violations(address)
        complaints = self.nyc311_client.get_complaints(address)

        # Detect changes
        changes = self._detect_changes(current_violations, bis_data, complaints)

        # Save new state
        if changes:
            self.violation_repo.save(address, bis_data)

        return {
            "address": address,
            "changes": changes,
            "violations": bis_data,
            "complaints": complaints
        }

    def check_all_addresses(self) -> dict:
        """Check all monitored addresses."""
        addresses = self.address_repo.get_all()
        results = []

        for addr in addresses:
            try:
                result = self.check_address(addr.address)
                results.append(result)

                # Send notifications if changes detected
                if result['changes']:
                    owner = self.address_repo.get_owner(addr.address)
                    if owner:
                        self.notification_service.notify_owner(owner, result['changes'])
            except Exception as e:
                logger.error(f"Check failed for {addr.address}", exc_info=e)

        return {"checked": len(results), "results": results}
```

### Phase 3: Refactor UI to Use Services

**Goal:** Decouple Streamlit from business logic

```python
# src/ui/app.py
import streamlit as st
from src.services.monitoring_service import MonitoringService
from src.services.address_service import AddressService
from src.ui.pages import dashboard, insights, addresses, owners, settings

# Dependency injection (simple version)
def get_monitoring_service() -> MonitoringService:
    # In production, use proper DI container
    return MonitoringService(
        address_repo=AddressRepository(),
        violation_repo=ViolationRepository(),
        bis_scraper=BISScraper(),
        nyc311_client=NYC311Client(),
        notification_service=NotificationService()
    )

def main():
    st.set_page_config(page_title="Building Monitor", layout="wide")

    # Navigation
    page = st.sidebar.selectbox("Navigation", [
        "Dashboard", "Insights", "Address Management", "Owner Management", "Settings"
    ])

    # Inject services
    monitoring_service = get_monitoring_service()

    # Route to pages
    if page == "Dashboard":
        dashboard.render(monitoring_service)
    elif page == "Insights":
        insights.render(monitoring_service)
    # ... etc
```

### Phase 4: Add API Layer (Parallel to UI)

**Goal:** Expose same functionality via REST API

```python
# src/api/main.py
from fastapi import FastAPI, Depends, HTTPException
from src.services.monitoring_service import MonitoringService
from src.api.dependencies import get_monitoring_service

app = FastAPI()

@app.post("/api/v1/checks")
async def trigger_check(
    address: str,
    service: MonitoringService = Depends(get_monitoring_service)
):
    try:
        result = service.check_address(address)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Now run both Streamlit UI and FastAPI in same container
# Or separate into microservices
```

### Final Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Presentation Layer                    │
│  ┌───────────────────┐      ┌──────────────────────┐   │
│  │  Streamlit UI     │      │   FastAPI REST API   │   │
│  │  (Port 8501)      │      │   (Port 8000)        │   │
│  └─────────┬─────────┘      └──────────┬───────────┘   │
└────────────┼────────────────────────────┼───────────────┘
             │                            │
             └──────────┬─────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│                 Service Layer                         │
│  MonitoringService | AddressService | OwnerService    │
│  NotificationService | ReportingService               │
└───────────────────────┬───────────────────────────────┘
                        │
       ┌────────────────┼────────────────┐
       │                │                │
┌──────▼─────┐  ┌──────▼──────┐  ┌─────▼──────┐
│ Repository │  │   Scrapers  │  │Notification│
│   Layer    │  │   & APIs    │  │  Handlers  │
│            │  │             │  │            │
│ Address    │  │ BIS Scraper │  │  Discord   │
│ Violation  │  │ 311 Client  │  │  Email     │
│ Owner      │  │ DOB Permits │  │  SMS       │
│ Complaint  │  └─────────────┘  └────────────┘
└──────┬─────┘
       │
┌──────▼──────────────────────────┐
│   Infrastructure Layer          │
│  ┌──────────┐    ┌───────────┐ │
│  │PostgreSQL│    │   Redis   │ │
│  │ Database │    │   Cache   │ │
│  └──────────┘    └───────────┘ │
└─────────────────────────────────┘
```

---

## Implementation Roadmap

### Sprint 1: Critical Fixes (Week 1-2) 🔴

**Priority:** Security & Stability

- [ ] **Remove hardcoded credentials**
  - Extract Zillow API key to environment variable
  - Extract Oxylabs proxy credentials to config
  - Remove/archive zillow_api.py if unused
- [ ] **Implement secrets management**
  - Add `.env` file support (python-dotenv)
  - Update docker-compose.yml for env vars
  - Document secret configuration
- [ ] **Fix Docker healthcheck**
  - Install curl in Dockerfile OR use Python-based check
  - Test healthcheck works
- [ ] **Add basic authentication to UI**
  - Install streamlit-authenticator
  - Add simple username/password protection
  - Document login credentials setup
- [ ] **Fix log rotation**
  - Replace FileHandler with RotatingFileHandler
  - Configure max size (10MB) and backup count (5)
- [ ] **Remove dead code**
  - Audit and remove unused utils modules
  - Remove duplicate workflow files
  - Clean up unused dependencies

**Deliverable:** Secure, stable application with no exposed secrets

---

### Sprint 2: Testing Infrastructure (Week 3-4) ✅

**Priority:** Enable safe refactoring

- [ ] **Set up pytest framework**
  - Add pytest, pytest-cov to requirements
  - Create tests/ directory structure
  - Add conftest.py with fixtures
- [ ] **Write unit tests for critical functions**
  - test_address_parser.py (address parsing logic)
  - test_bis_scraper.py (HTML parsing with mocked responses)
  - test_discord_notifications.py (webhook formatting)
- [ ] **Write integration tests**
  - test_database_operations.py (in-memory SQLite)
  - test_monitoring_service.py (end-to-end check with mocks)
- [ ] **Add CI test stage**
  - Update GitHub Actions to run tests
  - Fail builds on test failures
  - Add coverage reporting (Codecov)
- [ ] **Create test fixtures**
  - Sample BIS HTML responses
  - Sample 311 API JSON responses
  - Sample database states

**Deliverable:** 60%+ test coverage, CI pipeline runs tests

---

### Sprint 3: Architecture Refactoring (Week 5-8) 🏗️

**Priority:** Maintainability & Scalability

**Sprint 3.1: Extract Data Layer**
- [ ] Create data models (Address, Owner, Violation, Complaint)
- [ ] Create repository pattern base class
- [ ] Implement AddressRepository, OwnerRepository, ViolationRepository
- [ ] Migrate database queries from building_monitor.py to repositories
- [ ] Add database migration tool (Alembic)
- [ ] Write tests for repositories

**Sprint 3.2: Extract Core Logic**
- [ ] Create BISScraper class (extract from building_monitor.py)
- [ ] Create NYC311Client class
- [ ] Create Discord notification class
- [ ] Create NotificationService (unified interface)
- [ ] Write tests for scrapers and notifications

**Sprint 3.3: Create Service Layer**
- [ ] Create MonitoringService (orchestrates checking)
- [ ] Create AddressService (address management)
- [ ] Create OwnerService (owner management)
- [ ] Migrate business logic from building_monitor.py
- [ ] Write tests for services

**Sprint 3.4: Refactor UI**
- [ ] Update ui.py to use services instead of direct DB access
- [ ] Split ui.py into separate page modules
- [ ] Remove business logic from UI code
- [ ] Test UI still works end-to-end

**Deliverable:** Clean architecture with separated layers, 70%+ test coverage

---

### Sprint 4: Feature Enhancements (Week 9-12) ⭐

**Priority:** User value & Polish

- [ ] **Email notifications**
  - Integrate SendGrid or AWS SES
  - Create email templates
  - Add email config to owners
  - Test email delivery
- [ ] **SMS notifications**
  - Integrate Twilio
  - Add phone config to owners
  - Implement priority-based SMS (critical only)
  - Test SMS delivery
- [ ] **Per-owner scheduling**
  - Implement schedule parsing from owners.schedule
  - Update scheduler to respect per-owner times
  - Add schedule configuration to UI
- [ ] **Smart alerting & filtering**
  - Add alert preferences to owner model
  - Implement filtering logic (threshold, complaint types)
  - Add quiet hours support
  - Add digest mode (daily/weekly summaries)
- [ ] **Historical trend tracking**
  - Create violation_history table
  - Add snapshot on each check
  - Create trend query functions
  - Add trend charts to UI (Plotly)

**Deliverable:** Full notification suite, smart alerting, trend analysis

---

### Sprint 5: API & Integration (Week 13-15) 🔌

**Priority:** Extensibility

- [ ] **Add FastAPI**
  - Create api/ directory structure
  - Implement core endpoints (addresses, owners, checks)
  - Add OpenAPI documentation
  - Add authentication (API keys)
- [ ] **Health & metrics endpoints**
  - Implement /health endpoint
  - Add Prometheus metrics
  - Create Grafana dashboard
- [ ] **Webhooks (outbound)**
  - Allow users to register webhook URLs
  - Send check results to webhooks
  - Add webhook retry logic
- [ ] **Advanced NYC data integration**
  - Integrate DOB permits (utils/nyc_open_data.py)
  - Add crime statistics context
  - Add property valuation data (if Zillow API is valid)

**Deliverable:** REST API, monitoring dashboard, richer data context

---

### Sprint 6: Production Readiness (Week 16-18) 🚀

**Priority:** Reliability & Operations

- [ ] **PostgreSQL migration**
  - Set up PostgreSQL in docker-compose
  - Migrate schema from SQLite
  - Update repositories for PostgreSQL
  - Add connection pooling
  - Test performance improvements
- [ ] **Redis caching**
  - Add Redis to docker-compose
  - Implement caching layer
  - Cache BIN lookups (30 days)
  - Cache API responses (1 hour)
- [ ] **Observability**
  - Set up Sentry for error tracking
  - Implement structured logging (structlog)
  - Add Prometheus metrics throughout
  - Create Grafana dashboards
- [ ] **Backup & recovery**
  - Implement automated database backups
  - Set up backup to S3/cloud storage
  - Document restore procedure
  - Test disaster recovery
- [ ] **Documentation**
  - Write comprehensive README
  - API documentation (OpenAPI/Swagger)
  - Architecture decision records (ADRs)
  - Troubleshooting guide
  - Deployment guide

**Deliverable:** Production-grade application ready for scale

---

## Technology Recommendations

### Essential Libraries to Add

**Configuration:**
- `pydantic-settings` - Type-safe configuration management
- `python-dotenv` - Environment variable loading

**Testing:**
- `pytest` - Test framework
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking helpers
- `responses` or `vcrpy` - HTTP request mocking
- `freezegun` - Time mocking for scheduler tests

**Database:**
- `alembic` - Database migrations
- `sqlalchemy` - ORM (optional, but recommended for PostgreSQL)
- `psycopg2-binary` - PostgreSQL driver

**API:**
- `fastapi` - REST API framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation

**Caching:**
- `redis` - Redis client
- `hiredis` - Faster Redis parser

**Notifications:**
- `sendgrid` - Email sending
- `twilio` - SMS sending

**Reliability:**
- `tenacity` - Retry logic with exponential backoff
- `circuit-breaker` - Circuit breaker pattern

**Observability:**
- `structlog` - Structured logging
- `prometheus-client` - Metrics
- `sentry-sdk` - Error tracking

**Security:**
- `cryptography` - Encryption utilities
- `python-jose` - JWT tokens (for API auth)

### Database Considerations

**Stick with SQLite if:**
- Single user/owner
- Low check frequency (<10 addresses)
- Running on single machine (Unraid)
- Prefer simplicity

**Migrate to PostgreSQL if:**
- Multiple concurrent users
- >50 addresses monitored
- Need analytics/reporting
- Want to scale to multiple containers
- Need better backup/replication

---

## Cost-Benefit Analysis

### High ROI Improvements (Do First)

| Improvement | Effort | Impact | ROI |
|------------|--------|--------|-----|
| Remove hardcoded secrets | Low | Critical | ⭐⭐⭐⭐⭐ |
| Add basic auth to UI | Low | High | ⭐⭐⭐⭐⭐ |
| Fix Docker healthcheck | Low | Medium | ⭐⭐⭐⭐ |
| Add log rotation | Low | Medium | ⭐⭐⭐⭐ |
| Remove dead code | Low | Medium | ⭐⭐⭐⭐ |
| Add unit tests | Medium | High | ⭐⭐⭐⭐ |
| Implement email notifications | Low | High | ⭐⭐⭐⭐ |
| Extract repository layer | Medium | High | ⭐⭐⭐⭐ |

### Medium ROI Improvements (Do Second)

| Improvement | Effort | Impact | ROI |
|------------|--------|--------|-----|
| Create service layer | High | High | ⭐⭐⭐ |
| Add Redis caching | Medium | Medium | ⭐⭐⭐ |
| Implement SMS notifications | Low | Medium | ⭐⭐⭐ |
| Add trend analysis | Medium | Medium | ⭐⭐⭐ |
| Smart alerting/filtering | Medium | Medium | ⭐⭐⭐ |
| Add FastAPI | Medium | Medium | ⭐⭐⭐ |

### Lower ROI Improvements (Do Later)

| Improvement | Effort | Impact | ROI |
|------------|--------|--------|-----|
| Migrate to PostgreSQL | High | Low-Medium | ⭐⭐ |
| Full observability stack | High | Medium | ⭐⭐ |
| Advanced NYC data integration | Medium | Low | ⭐⭐ |
| PDF reporting | Medium | Low | ⭐⭐ |
| Webhook integrations | Medium | Low | ⭐ |

---

## Conclusion

This **Building Monitor** project is a functional MVP that successfully achieves its core objective of monitoring NYC buildings and sending Discord notifications. However, as a rapidly-developed prototype, it suffers from common technical debt issues:

**Strengths:**
- ✅ Working core functionality
- ✅ Docker containerization
- ✅ Automated CI/CD pipeline
- ✅ Basic web UI for management

**Critical Gaps:**
- 🔴 Security vulnerabilities (exposed credentials)
- 🔴 No testing infrastructure
- 🔴 Monolithic architecture
- 🔴 ~40% dead code
- 🔴 Poor error handling

**Recommended Approach:**

1. **Phase 1 (Weeks 1-2):** Address critical security issues immediately
2. **Phase 2 (Weeks 3-4):** Build testing infrastructure before refactoring
3. **Phase 3 (Weeks 5-8):** Refactor to clean architecture incrementally
4. **Phase 4 (Weeks 9-12):** Add high-value features (email, SMS, trends)
5. **Phase 5 (Weeks 13-15):** Add API layer for extensibility
6. **Phase 6 (Weeks 16-18):** Production hardening (observability, backups)

This roadmap transforms the project from a quick prototype into a **production-grade, maintainable, secure application** over 18 weeks (~4.5 months) of focused development.

**Total Estimated Effort:** 18-20 weeks (assuming 1 full-time developer)

**Alternative Fast-Track (6 weeks):**
- Week 1-2: Critical fixes only (security, stability)
- Week 3-4: Minimum testing + refactor data layer
- Week 5-6: Email notifications + basic API

This fast-track approach addresses the most critical issues and adds the most-requested features while keeping technical debt manageable.

---

*Document prepared: November 19, 2025*
*For questions or clarifications, please consult the original codebase analysis or architectural diagrams.*
