import pandas as pd
from datetime import date, timedelta
from typing import Iterable, List, Tuple, Optional
import time

def chunk_date_ranges(start: date, end: date, chunk_days: int = 30) -> List[Tuple[date, date]]:
	"""Divide un rango [start, end] en sub-rangos de hasta chunk_days días (incluidos).
	Retorna lista de tuplas (ini, fin) contiguas y no superpuestas.
	"""
	if start > end:
		return []
	ranges = []
	cur = start
	while cur <= end:
		seg_end = min(cur + timedelta(days=chunk_days - 1), end)
		ranges.append((cur, seg_end))
		cur = seg_end + timedelta(days=1)
	return ranges

def fetch_gene_recurso_chunked(objetoAPI, start: date, end: date, filtros: Iterable[str], batch_size: int = 50, chunk_days: int = 180, retries: int = 2, backoff_sec: float = 0.8) -> pd.DataFrame:
	"""Consulta Gene con Entity='Recurso' para una lista de filtros (SIC) en lotes y por chunks de fechas.
	Devuelve DataFrame con columnas: ['Codigo','Fecha','Generacion_GWh'] agregadas por día.
	OPTIMIZADO: Usa cache manager para evitar consultas repetidas a API.
	MEJORA DE PERFORMANCE: chunk_days dinámico según tamaño del rango.
	"""
	from utils._xm import fetch_metric_data
	from utils.cache_manager import get_cache_key, get_from_cache, save_to_cache
	import logging
	logger = logging.getLogger(__name__)
	
	filtros = [str(x).strip() for x in filtros if x and isinstance(x, (str, int))]
	if not filtros:
		return pd.DataFrame(columns=['Codigo','Fecha','Generacion_GWh'])

	# OPTIMIZACIÓN: Cachear resultado completo de consulta
	filtros_hash = hash(tuple(sorted(filtros)))
	cache_key = get_cache_key('gene_recurso_chunked', filtros_hash, start, end)
	cached_data = get_from_cache(cache_key, allow_expired=False)
	if cached_data is not None:
		logger.info(f"✅ Cache válido para Gene/Recurso ({len(filtros)} códigos, {start} a {end})")
		return cached_data

	# OPTIMIZACIÓN V2: Chunk days dinámico según rango total
	total_days = (end - start).days
	if total_days <= 60:
		chunk_days = total_days  # 1 consulta para rangos cortos
		logger.info(f"📊 Rango corto ({total_days} días) - 1 consulta")
	elif total_days <= 180:
		chunk_days = 90  # 2 consultas para rango medio
		logger.info(f"📊 Rango medio ({total_days} días) - ~{(total_days//90)+1} consultas")
	elif total_days <= 365:
		chunk_days = 180  # 2-3 consultas para 1 año
		logger.info(f"📊 Rango grande ({total_days} días) - ~{(total_days//180)+1} consultas")
	else:
		chunk_days = 365  # Max 365 días por chunk para rangos muy grandes
		logger.info(f"📊 Rango muy grande ({total_days} días) - ~{(total_days//365)+1} consultas")
	
	# OPTIMIZACIÓN V3: Reducir batch_size para rangos grandes (evitar timeouts)
	if total_days > 365:
		batch_size = 30  # Lotes más pequeños para rangos >1 año
		backoff_sec = 1.2  # Más pausa entre requests
		logger.info(f"⚠️ Rango >1 año: batch_size reducido a {batch_size} para estabilidad")
	elif total_days > 180:
		batch_size = 40  # Lotes medianos para rangos >6 meses
		backoff_sec = 1.0
	
	import time
	registros = []
	total_batches = sum(1 for _ in chunk_date_ranges(start, end, chunk_days=chunk_days) for _ in range(0, len(filtros), batch_size))
	batch_count = 0
	
	for ini, fin in chunk_date_ranges(start, end, chunk_days=chunk_days):
		# Batches por códigos SIC
		for i in range(0, len(filtros), batch_size):
			batch_count += 1
			lote = filtros[i:i+batch_size]
			
			# OPTIMIZACIÓN: Backoff entre batches para evitar saturar API
			if batch_count > 1:
				time.sleep(backoff_sec)
			
			# Log de progreso para rangos grandes
			if total_batches > 5 and batch_count % 5 == 0:
				logger.info(f"📊 Progreso: {batch_count}/{total_batches} batches completados")
			
			# Usar la API directamente con códigos específicos
			df = objetoAPI.request_data("Gene", "Recurso", ini, fin, lote)
			if df is None or df.empty:
				continue
			horas_cols = [c for c in df.columns if str(c).startswith('Values_Hour')]
			if not horas_cols:
				continue
			# Identificar columna de código en respuesta Gene (puede variar)
			code_col = None
			for cand in ('Values_code', 'Values_Code', 'Values_resourceCode', 'Values_ResourceCode'):
				if cand in df.columns:
					code_col = cand
					break
			for _, row in df.iterrows():
				try:
					kwh = sum(float(row.get(c)) for c in horas_cols if pd.notna(row.get(c)))
				except Exception:
					kwh = 0.0
				registros.append({
					'Codigo': str(row.get(code_col, '') if code_col else '').strip(),
					'Fecha': row.get('Date'),
					'Generacion_GWh': kwh/1_000_000.0
				})

	if not registros:
		return pd.DataFrame(columns=['Codigo','Fecha','Generacion_GWh'])
	
	df_out = pd.DataFrame(registros)
	# Asegurar tipos/orden básico
	if 'Fecha' in df_out.columns:
		try:
			df_out['Fecha'] = pd.to_datetime(df_out['Fecha']).dt.date
		except Exception:
			pass
	
	# Cachear resultado por 6 horas (datos de generación actualizados diariamente)
	save_to_cache(cache_key, df_out, cache_type='gene_recurso')
	logger.info(f"✅ Cacheado Gene/Recurso: {len(df_out)} registros ({len(filtros)} códigos)")
	
	return df_out

