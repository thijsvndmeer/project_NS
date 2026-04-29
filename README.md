# NS Punctualiteit & Weer

**How do weather conditions correlate with NS train punctuality?**

This project is a data engineering study conducted at the University of Amsterdam (UvA). It collects real-time NS train departure data and KNMI meteorological observations, stores them in a relational MySQL database, and analyses how different weather conditions relate to train delays.

---

## Research Questions

1. What is the correlation between **precipitation** and train delay?
2. Which **routes** are most sensitive to wind?
3. How does **snow** affect total service cancellations?

---

## Architecture

```
┌─────────────────────┐      ┌──────────────────────┐
│  NS Reisinformatie  │      │  KNMI Open Data API  │
│  API  (departures)  │      │  (10-min observations)│
└────────┬────────────┘      └──────────┬───────────┘
         │ NS.py / main.py              │ weather_collection.py
         ▼                              ▼
         └──────────── MySQL DB ────────┘
                  (nsdatabase)
                       │
              weather_processing.ipynb
                       │
                  Analysis / Poster
```

### Database Schema (3NF)

| Table      | Key columns                                     |
|------------|-------------------------------------------------|
| `location` | id, naam, lat, lon                              |
| `station`  | id, naam, locatie (FK→location), uic            |
| `stop`     | id, station (FK→station), vertraging_vertrek, richting, vertrek |
| `weer`     | id, locatie (FK→location), type (FK→weertype), tijd |
| `weertype` | naam (DP, DM, DT, MP, MM, MT, Null)             |

Weather types use the **SSC2 (Spatial Synoptic Classification)** scheme:
`DP` = Dry Polar · `DM` = Dry Moderate · `DT` = Dry Tropical  
`MP` = Moist Polar · `MM` = Moist Moderate · `MT` = Moist Tropical

---

## Project Files

| File | Description |
|------|-------------|
| `NS.py` | NS API helper functions and database I/O |
| `main.py` | Main data-collection loop (NS train stops) |
| `weather_collection.py` | KNMI NetCDF downloader and CSV converter |
| `seeddays.py` | SSC2 seed-day generator from KNMI daily data |
| `weather_processing.ipynb` | Notebook: classify weather and write to DB |
| `dutch_seeds.csv` | Pre-computed SSC2 seed values for the Netherlands |
| `nsdatabase.sql` | Full MySQL schema + data dump |
| `poster_v5.html` | Academic A0 poster (HTML/CSS) |
| `style_v5.css` | Poster stylesheet |
| `weather_data/` | Downloaded KNMI NetCDF & CSV files |
| `nsdatabase/` | MySQL InnoDB table files (`.ibd`) |

---

## Setup

### Requirements

- Python 3.10+
- MySQL 8.0+
- Python packages: `mysql-connector-python`, `requests`, `pandas`, `numpy`, `netCDF4`

```bash
pip install mysql-connector-python requests pandas numpy netCDF4
```

### Database

1. Create the database and import the schema/data:
   ```bash
   mysql -u root -p -e "CREATE DATABASE NSdatabase;"
   mysql -u root -p NSdatabase < nsdatabase.sql
   ```
2. Create a MySQL user (or use root) and set credentials via environment variables (see below).

### Environment Variables

The scripts read credentials from environment variables to avoid hardcoding secrets:

```bash
export NS_API_KEY="your_ns_subscription_key"
export KNMI_API_KEY="your_knmi_api_key"
export DB_HOST="localhost"
export DB_USER="your_db_user"
export DB_PASSWORD="your_db_password"
export DB_NAME="NSdatabase"
```

---

## Usage

### Collect NS train departure data

```bash
python main.py
```

Enter the desired collection duration in minutes when prompted. The script polls every ~4 minutes and records departures within a 5-minute window.

### Collect KNMI weather data

```bash
python weather_collection.py
```

Downloads the latest 10-minute KNMI observation file (NetCDF), converts it to CSV, and saves both to `weather_data/`.

### Generate SSC2 seed values

```bash
python seeddays.py --file path/to/knmi_daily.txt --output dutch_seeds.csv
```

### Process weather into database

Open and run `weather_processing.ipynb` in Jupyter after collecting weather CSVs.

---

## Authors

Wesley van den Engh · Jens Groen · Thijs van der Meer · Tijs Voorsteegh  
UvA — Data Management & Engineering
