import sys
import os
import pandas as pd
sys.path.append(os.getcwd())

from domain.services.transmission_service import TransmissionService

print("Verificando TransmissionService...")
try:
    service = TransmissionService()
    df = service.get_transmission_lines()
    print(f"Service returned DataFrame with shape: {df.shape}")
    if not df.empty:
        print("Columns:", df.columns.tolist())
        print("First row:", df.iloc[0].to_dict())
    else:
        print("DataFrame is empty.")
except Exception as e:
    print(f"Error executing service: {e}")
