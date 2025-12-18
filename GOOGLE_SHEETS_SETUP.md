# Google Sheets Integration Setup

## Overview
The app now supports integrating historical RKT stock price data from a Google Sheet, which will be merged with live API data.

## Setup Instructions

### 1. Prepare Your Google Sheet
Your Google Sheet should have this format:

```
Date          | Close
2024-01-01    | 15.23
2024-01-02    | 15.45
2024-01-03    | 15.67
...
```

**Requirements:**
- First column: Date (any common date format)
- Second column: Close price (numeric)
- Column headers can have any name

### 2. Share Your Sheet
1. Open your Google Sheet
2. Click "Share" in the top-right
3. Change permissions to "Anyone with the link can view"
4. Click "Copy link"

### 3. Get the Export URL
Your share link looks like:
```
https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit#gid=GID_NUMBER
```

Convert it to a CSV export URL:
```
https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/export?format=csv&gid=GID_NUMBER
```

**Example:**
- Share link: `https://docs.google.com/spreadsheets/d/1abc123XYZ/edit#gid=0`
- Export URL: `https://docs.google.com/spreadsheets/d/1abc123XYZ/export?format=csv&gid=0`

### 4. Update app.py
Open `app.py` and find line ~158:

```python
SHEET_URL = None  # TODO: Replace with your Google Sheet CSV export URL
```

Replace `None` with your export URL:

```python
SHEET_URL = "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/export?format=csv&gid=0"
```

### 5. Test
Run your app - the RKT chart should now show:
- Historical data from your Google Sheet (cached for 24 hours)
- Recent live data from Alpha Vantage API (cached for 1 hour)
- Merged dataset with live data taking precedence for overlapping dates

## Notes
- Historical data is cached for 24 hours (since it rarely changes)
- Live API data is cached for 1 hour
- The merged dataset is limited to 180 days for memory efficiency
- Chart displays only the last 90 days for optimal performance
