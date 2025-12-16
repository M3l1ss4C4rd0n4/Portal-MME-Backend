"""
Módulo para cargar y procesar datos para Dash
"""
import pandas as pd
from io import BytesIO

def to_excel(df):
    """Convertir DataFrame a Excel"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
    processed_data = output.getvalue()
    return processed_data
