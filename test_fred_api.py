#!/usr/bin/env python3
"""
Test script to verify FRED API integration works correctly.
Usage:
  Without API key: python test_fred_api.py
  With API key:    FRED_API_KEY=your_key python test_fred_api.py
"""

import os
import requests
import pandas as pd
import io

def test_fred_api():
    fred_api_key = os.environ.get('FRED_API_KEY', '')

    print("=" * 60)
    print("FRED API Integration Test")
    print("=" * 60)
    print(f"API Key configured: {'✅ YES' if fred_api_key else '❌ NO'}")
    print()

    # Test one series
    series_id = "MORTGAGE30US"
    series_name = "30Y Fixed"

    if fred_api_key:
        # Test official API endpoint
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={fred_api_key}&file_type=json"
        print(f"Testing: Official FRED API (with key)")
        print(f"URL: {url.replace(fred_api_key, 'XXXXX')}")

        try:
            r = requests.get(url, timeout=30)
            print(f"Status: {r.status_code}")
            r.raise_for_status()

            data = r.json()
            if 'observations' in data:
                obs_count = len(data['observations'])
                print(f"✅ SUCCESS: Got {obs_count} observations")

                # Parse data
                obs_data = [(o['date'], float(o['value']) if o['value'] != '.' else None)
                            for o in data['observations']]
                df = pd.DataFrame(obs_data, columns=['DATE', series_name])
                df['DATE'] = pd.to_datetime(df['DATE'])
                df[series_name] = pd.to_numeric(df[series_name], errors='coerce')

                print(f"DataFrame shape: {df.shape}")
                print("\nLatest 3 values:")
                print(df.tail(3).to_string())
            else:
                print(f"❌ ERROR: No 'observations' in response")
                print(f"Response keys: {data.keys()}")
        except Exception as e:
            print(f"❌ ERROR: {e}")
    else:
        # Test CSV export endpoint
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        print(f"Testing: CSV Export (no key)")
        print(f"URL: {url}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            r = requests.get(url, headers=headers, timeout=30)
            print(f"Status: {r.status_code}")
            r.raise_for_status()

            df = pd.read_csv(io.StringIO(r.text))
            date_col, val_col = df.columns[0], df.columns[1]

            print(f"✅ SUCCESS: Got {len(df)} rows")
            print(f"Columns: {list(df.columns)}")
            print("\nLatest 3 values:")
            print(df.tail(3).to_string())

        except Exception as e:
            print(f"❌ ERROR: {e}")

    print()
    print("=" * 60)
    if not fred_api_key:
        print("💡 TIP: Get free API key at:")
        print("   https://fred.stlouisfed.org/docs/api/api_key.html")
        print("   Then run: FRED_API_KEY=your_key python test_fred_api.py")

if __name__ == "__main__":
    test_fred_api()
