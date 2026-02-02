
import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.insert(0, '/home/admonctrlxm/server')

from infrastructure.database.repositories.transmission_repository import TransmissionRepository

repo = TransmissionRepository()
latest_date_str = repo.get_latest_date()
print(f"Latest date in DB (str): {latest_date_str}")

if latest_date_str:
    latest_dt = pd.to_datetime(latest_date_str)
    print(f"Latest date parsed: {latest_dt}")
    
    now = datetime.now()
    print(f"Current time: {now}")
    
    days_old = (now - latest_dt).days
    print(f"Days old: {days_old}")
    
    if days_old <= 7:
        print("Status: FRESH")
    else:
        print("Status: STALE")
else:
    print("No data in DB")
