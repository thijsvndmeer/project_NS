import os
import time
import logging
import requests
import json
import mysql.connector
import netCDF4
import numpy as np
from datetime import datetime, timedelta

# Configuration
API_KEY = "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjU3OTNkYmExYWQxMjQwYjY4MzM0ZjNkZThiMjI1YWFjIiwiaCI6Im11cm11cjEyOCJ9"
DATASET_NAME = "10-minute-in-situ-meteorological-observations"
DATASET_VERSION = "1.0"
DOWNLOAD_DIRECTORY = "weather_data"
BASE_URL = "https://api.dataplatform.knmi.nl/open-data/v1"

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin',
    'password': 'NS-server2026',
    'database': 'NSdatabase'
}

# Potential Column Mappings (NetCDF Variable -> Possible Database Columns)
# We prioritize exact matches, then fallbacks.
VAR_MAPPING = {
    'station': ['station', 'stn', 'station_id', 'station_code'],
    'time': ['tijd', 'time', 'datum', 'date', 'datetime', 'timestamp'],
    'ta': ['temperatuur', 'temp', 'ta', 'temperature', 'air_temperature'],
    'rh': ['luchtvochtigheid', 'hum', 'rh', 'humidity', 'relative_humidity'],
    'ff': ['wind_snelheid', 'wind_speed', 'ff', 'ws'],
    'dd': ['wind_richting', 'wind_direction', 'dd', 'wd'],
    'pp': ['luchtdruk', 'pressure', 'pp', 'air_pressure', 'pres'],
    'D1H': ['neerslag_duur', 'rainfall_duration', 'd1h'],
    'R1H': ['neerslag', 'rainfall', 'r1h', 'rain'],
    'pg': ['neerslag_intensiteit', 'precip_intensity', 'pg']
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class KNMIAPI:
    def __init__(self, api_token: str):
        self.headers = {"Authorization": api_token}
        self.base_url = BASE_URL

    def list_files(self, dataset_name: str, dataset_version: str, params: dict):
        url = f"{self.base_url}/datasets/{dataset_name}/versions/{dataset_version}/files"
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing files: {e}")
            return None

    def get_file_url(self, dataset_name: str, dataset_version: str, file_name: str):
        url = f"{self.base_url}/datasets/{dataset_name}/versions/{dataset_version}/files/{file_name}/url"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting file URL: {e}")
            return None

def download_file(download_url, filepath):
    try:
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Successfully downloaded to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        return False

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        logger.error(f"Database connection failed: {err}")
        return None

def get_table_columns(cursor, table_name):
    try:
        cursor.execute(f"DESCRIBE {table_name}")
        return [row[0] for row in cursor.fetchall()]
    except mysql.connector.Error as err:
        logger.error(f"Error describing table {table_name}: {err}")
        return []

def map_columns(db_columns):
    final_map = {}
    for nc_var, possible_names in VAR_MAPPING.items():
        for name in possible_names:
            if name in db_columns:
                final_map[nc_var] = name
                break
    return final_map

def process_nc_file(filepath):
    logger.info(f"Processing {filepath} for database insertion...")
    
    conn = get_db_connection()
    if not conn:
        logger.error("Skipping DB insertion due to connection handling.")
        return

    cursor = conn.cursor()
    table_name = 'weer'
    
    # 1. Determine mapping
    db_cols = get_table_columns(cursor, table_name)
    if not db_cols:
        logger.error(f"Could not retrieve columns for table '{table_name}'. Skipping.")
        conn.close()
        return
        
    logger.info(f"Found table '{table_name}' columns: {db_cols}")
    
    col_map = map_columns(db_cols)
    if not col_map:
        logger.warning("No valid columns mapped! Check table schema vs script mapping.")
        conn.close()
        return
    
    logger.info(f"Column mapping: {col_map}")

    # 2. Open NetCDF
    try:
        ds = netCDF4.Dataset(filepath)
    except Exception as e:
        logger.error(f"Failed to open NetCDF file: {e}")
        conn.close()
        return

    try:
        # 3. Extract Data
        # Ensure we have station and time
        if 'station' not in ds.variables:
            logger.error("NetCDF file missing 'station' variable.")
            ds.close()
            conn.close()
            return
            
        nc_stations = ds.variables['station'][:]
        # Helper to decode bytes if necessary
        stations = []
        for s in nc_stations:
            if isinstance(s, bytes):
                stations.append(s.decode('utf-8').strip())
            else:
                stations.append(str(s))
        
        # Time handling
        # Assuming typical KNMI structure: time dimension size 1, station dimension size N
        # time variable usually has units "seconds since ..."
        
        nc_time_var = ds.variables.get('time')
        if nc_time_var:
            try:
                # Get the single time value
                time_val = nc_time_var[0] 
                # Convert to Python datetime
                # Handle cases where units might be missing or standard
                if hasattr(nc_time_var, 'units'):
                    date_obj = netCDF4.num2date(time_val, units=nc_time_var.units)
                else:
                    # Fallback default for KNMI logic if units missing (rare)
                    # Often "seconds since 1950-01-01 00:00:00"
                    date_obj = netCDF4.num2date(time_val, units="seconds since 1950-01-01 00:00:00")
            except Exception as e:
                logger.warning(f"Time conversion issue: {e}. Using current time.")
                date_obj = datetime.now()
        else:
            date_obj = datetime.now()

        # Build base Insert Query
        # We insert one row per station
        
        # Prepare lists for batch insert
        # We need to construct the SQL statement first
        
        # Columns to insert into
        target_cols = list(col_map.values())
        placeholders = ["%s"] * len(target_cols)
        sql = f"INSERT INTO {table_name} ({', '.join(target_cols)}) VALUES ({', '.join(placeholders)})"
        
        # We need to handle duplicates? "ON DUPLICATE KEY UPDATE" or "IGNORE"? 
        # User implies collecting history, so insert. Primary key usually prevents duplicates.
        # Let's use INSERT IGNORE to be safe if PK exists.
        sql = f"INSERT IGNORE INTO {table_name} ({', '.join(target_cols)}) VALUES ({', '.join(placeholders)})"

        rows_to_insert = []
        
        # Iterate over stations (indices)
        for i, station_code in enumerate(stations):
            row_data = []
            valid_row = True
            
            for nc_var, db_col in col_map.items():
                val = None
                
                if nc_var == 'station':
                    val = station_code
                elif nc_var == 'time':
                    val = date_obj
                else:
                    # Variable from NetCDF
                    if nc_var in ds.variables:
                        # shape is usually (time, station) or just (station)
                        var_data = ds.variables[nc_var]
                        # Check dimensions
                        if 'station' in var_data.dimensions:
                            # Assuming logical layout (time, station) or (station)
                            # inspect_nc showed time:1, station:52.
                            # So variables probably (time, station) -> [0, i]
                            # OR (station) -> [i]
                            
                            dims = var_data.dimensions
                            try:
                                if dims == ('time', 'station'):
                                    val = var_data[0, i]
                                elif dims == ('station',):
                                    val = var_data[i]
                                elif dims == ('station', 'time'): # unlikely
                                    val = var_data[i, 0]
                                else:
                                    # Fallback: flatten and take i if size matches?
                                    if var_data.size == len(stations):
                                        val = var_data.flatten()[i]
                            except Exception:
                                val = None
                        
                        # Handle MaskedConstant (missing data)
                        if val is not None and np.ma.is_masked(val):
                            val = None
                        
                        # Convert numpy types to python native
                        if isinstance(val, (np.floating, float)):
                            val = float(val)
                        elif isinstance(val, (np.integer, int)):
                            val = int(val)
                            
                    else:
                        val = None
                
                row_data.append(val)
            
            rows_to_insert.append(tuple(row_data))
        
        # Execute Batch Insert
        if rows_to_insert:
            logger.info(f"Inserting {len(rows_to_insert)} rows into {table_name}...")
            cursor.executemany(sql, rows_to_insert)
            conn.commit()
            logger.info("Insertion complete.")
        else:
            logger.warning("No rows prepared for insertion.")
            
    except Exception as e:
        logger.error(f"Error during processing/insertion: {e}")
    finally:
        ds.close()
        cursor.close()
        conn.close()

def main():
    # Ensure download directory exists
    if not os.path.exists(DOWNLOAD_DIRECTORY):
        os.makedirs(DOWNLOAD_DIRECTORY)
        logger.info(f"Created directory: {DOWNLOAD_DIRECTORY}")

    api = KNMIAPI(API_KEY)
    
    logger.info(f"Starting weather data collection for dataset: {DATASET_NAME}")
    
    while True:
        try:
            # Request the latest file
            params = {"maxKeys": 1, "orderBy": "created", "sorting": "desc"}
            result = api.list_files(DATASET_NAME, DATASET_VERSION, params)

            if result and "files" in result and len(result["files"]) > 0:
                latest_file_info = result["files"][0]
                filename = latest_file_info["filename"]
                filepath = os.path.join(DOWNLOAD_DIRECTORY, filename)

                if not os.path.exists(filepath):
                    logger.info(f"Downloading new file: {filename}...")
                    url_result = api.get_file_url(DATASET_NAME, DATASET_VERSION, filename)
                    
                    if url_result and "temporaryDownloadUrl" in url_result:
                        download_url = url_result["temporaryDownloadUrl"]
                        success = download_file(download_url, filepath)
                        if success:
                            # Trigger processing immediately after download
                            process_nc_file(filepath)
                    else:
                        logger.error("Failed to retrieve temporary download URL.")
                else:
                    logger.info(f"File {filename} already exists. Checking if processing is needed (optional, skipping for now).")
                    # Optionally we could force process here if DB is missing data, 
                    # but typically we just wait for new files.
            else:
                logger.warning("No files returned by the API.")

        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")

        logger.info("Waiting 10 minutes for the next update...")
        time.sleep(600)

if __name__ == "__main__":
    main()
