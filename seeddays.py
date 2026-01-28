import pandas as pd
import numpy as np
import argparse
import io
import requests

def calculate_seeds(df):
    anchor_months = [1, 4, 7, 10]
    results = []

    for month in anchor_months:
        m_data = df[df['date'].dt.month == month].copy()
        if m_data.empty: continue

        # Divide into Dry and Moist using Median Dewpoint
        median_dwp = m_data['dewpoint'].median()
        dry_subset = m_data[m_data['dewpoint'] <= median_dwp]
        moist_subset = m_data[m_data['dewpoint'] > median_dwp]

        # Calculate Means for the 6 types (12 values total per month)
        dp = dry_subset.nsmallest(5, 'temp').mean(numeric_only=True)
        dt = dry_subset.nlargest(5, 'temp').mean(numeric_only=True)
        dm_idx = len(dry_subset)//2
        dm = dry_subset.iloc[max(0, dm_idx-2):dm_idx+3].mean(numeric_only=True)

        mp = moist_subset.nsmallest(5, 'temp').mean(numeric_only=True)
        mt = moist_subset.nlargest(5, 'dewpoint').mean(numeric_only=True)
        mm_idx = len(moist_subset)//2
        mm = moist_subset.iloc[max(0, mm_idx-2):mm_idx+3].mean(numeric_only=True)

        results.append({
            'month': month,
            'DP_temp': round(dp['temp'], 2), 'DP_dewp': round(dp['dewpoint'], 2),
            'DM_temp': round(dm['temp'], 2), 'DM_dewp': round(dm['dewpoint'], 2),
            'DT_temp': round(dt['temp'], 2), 'DT_dewp': round(dt['dewpoint'], 2),
            'MP_temp': round(mp['temp'], 2), 'MP_dewp': round(mp['dewpoint'], 2),
            'MM_temp': round(mm['temp'], 2), 'MM_dewp': round(mm['dewpoint'], 2),
            'MT_temp': round(mt['temp'], 2), 'MT_dewp': round(mt['dewpoint'], 2)
        })
    return pd.DataFrame(results)

def main():
    parser = argparse.ArgumentParser(description='KNMI SSC2 Seed Generator')
    parser.add_argument('--file', help='Path to downloaded KNMI txt/csv file')
    parser.add_argument('--output', default='knmi_seeds.csv', help='Output filename')
    args = parser.parse_args()

    if not args.file:
        print("[!] Please provide a KNMI data file using --file path/to/data.txt")
        return

    print(f"--- Processing KNMI Data from {args.file} ---")

    try:
        # KNMI files usually have a long header. Skip rows starting with '#'
        # and handle the 'TG' and 'TD' columns.
        df = pd.read_csv(args.file, skipinitialspace=True, comment='#')

        # Clean column names (KNMI often adds leading spaces)
        df.columns = df.columns.str.strip()

        # Convert KNMI Date (YYYYMMDD) to datetime
        df['date'] = pd.to_datetime(df['YYYYMMDD'], format='%Y%m%d')

        # Convert 0.1C to Celsius (TG=Mean Temp, TD=Mean Dewpoint)
        # Note: If TD is missing in your file, ensure you downloaded 'Dew Point' from KNMI
        df['temp'] = df['TG'] / 10.0
        df['dewpoint'] = df['TD'] / 10.0

        # Run Calculation
        seed_df = calculate_seeds(df)

        # Save
        seed_df.to_csv(args.output, index=False)
        print(f"[SUCCESS] 12-value seed dataset saved to {args.output}")
        print(seed_df)

    except Exception as e:
        print(f"[ERROR] Could not parse file. Check if 'TG' and 'TD' are present. \nDetails: {e}")

if __name__ == "__main__":
    main()
