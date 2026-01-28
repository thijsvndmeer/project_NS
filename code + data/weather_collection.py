import os
import time
import logging
import requests
import json
import netCDF4
import numpy as np
import csv
from datetime import datetime, timedelta

# Configuration
API_KEY = "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjU3OTNkYmExYWQxMjQwYjY4MzM0ZjNkZThiMjI1YWFjIiwiaCI6Im11cm11cjEyOCJ9"
DATASET_NAME = "10-minute-in-situ-meteorological-observations"
DATASET_VERSION = "1.0"
DOWNLOAD_DIRECTORY = "weather_data"
BASE_URL = "https://api.dataplatform.knmi.nl/open-data/v1"



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





def process_nc_file(filepath):
    logger.info(f"Processing {filepath} for CSV conversion...")
    csv_filepath = filepath + '.csv'
    
    try:
        ds = netCDF4.Dataset(filepath)
    except Exception as e:
        logger.error(f"Failed to open NetCDF file: {e}")
        return

    try:
        header = list(ds.variables.keys())
        
        # Get number of stations
        num_stations = 0
        if 'station' in ds.variables:
            num_stations = len(ds.variables['station'])
        else:
            # Try to infer from a variable with a 'station' dimension
            for var_name, var in ds.variables.items():
                if 'station' in var.dimensions:
                    num_stations = ds.dimensions['station'].size
                    break
        
        if num_stations == 0:
            logger.warning(f"Could not determine number of stations in {filepath}. Skipping.")
            ds.close()
            return
            
        with open(csv_filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            
            rows_to_insert = []
            
            for i in range(num_stations):
                row_data = {}
                for var_name in header:
                    var = ds.variables[var_name]
                    val = None
                    
                    try:
                        # A variable can be scalar, 1D, 2D, etc.
                        # We try to extract the value that corresponds to the i-th station
                        if 'station' in var.dimensions:
                            # The variable is indexed by station
                            s_index = var.dimensions.index('station')
                            
                            # Create a slicer tuple
                            slicer = [slice(None)] * len(var.dimensions)
                            slicer[s_index] = i
                            
                            # For other dimensions, take the first element (e.g., time)
                            for d_idx, dim_name in enumerate(var.dimensions):
                                if dim_name != 'station':
                                    slicer[d_idx] = 0 # Take first element for other dimensions
                            
                            val = var[tuple(slicer)]

                        elif len(var.shape) > 0 and var.shape[0] == num_stations:
                             # Guessing that this variable is also indexed by station
                             val = var[i]
                        else:
                            # Not indexed by station, so repeat the value for each station
                            # Take the first element if it's an array
                            if hasattr(var, 'flatten'):
                                flat_var = var[:].flatten()
                                if flat_var.size > 0:
                                    val = flat_var[0]
                            else:
                                val = var[()]


                    except Exception:
                        val = None

                    # convert to python native types
                    if val is not None and np.ma.is_masked(val):
                        val = None
                    
                    if isinstance(val, (np.floating, float)):
                        val = float(val)
                    elif isinstance(val, (np.integer, int)):
                        val = int(val)
                    elif isinstance(val, bytes):
                        val = val.decode('utf-8').strip()

                    row_data[var_name] = val
                    
                rows_to_insert.append(row_data)

            if rows_to_insert:
                logger.info(f"Writing {len(rows_to_insert)} rows to {csv_filepath}...")
                writer.writerows(rows_to_insert)
                logger.info("CSV writing complete.")
            else:
                logger.warning("No rows prepared for writing.")
            
    except Exception as e:
        logger.error(f"Error during processing/writing: {e}")
    finally:
        ds.close()

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
