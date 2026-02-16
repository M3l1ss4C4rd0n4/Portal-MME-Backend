"""
Chart Generator Service
Genera gráficos dinámicos para enviar por WhatsApp
"""
import logging
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
from io import BytesIO
import uuid
import os
from pathlib import Path

from app.config import settings
from services.data_service import DataService

logger = logging.getLogger(__name__)


class ChartService:
    """
    Servicio de generación de gráficos
    """
    
    def __init__(self):
        self.data_service = DataService()
        self.output_dir = settings.DATA_DIR / "charts"
        self.output_dir.mkdir(exist_ok=True)
    
    async def generate_chart(
        self,
        metric: str,
        chart_type: str = "line",
        period: str = "7d",
        title: Optional[str] = None
    ) -> str:
        """
        Genera gráfico y retorna ruta local
        
        Args:
            metric: Código de métrica (Gene, DemaReal, PrecioBolsa, etc)
            chart_type: line, bar, pie, area
            period: 7d, 30d, 90d, 1y
            title: Título personalizado
        
        Returns:
            Ruta al archivo de imagen generado
        """
        try:
            logger.info(f"Generando gráfico: {metric}, tipo: {chart_type}, período: {period}")
            
            # Obtener datos
            days = self._parse_period(period)
            data = await self.data_service.get_metric_data(metric, days=days)
            
            if not data:
                raise ValueError(f"No hay datos disponibles para {metric}")
            
            # Crear DataFrame
            df = pd.DataFrame(data)
            
            # Crear figura según tipo
            if chart_type == "line":
                fig = self._create_line_chart(df, metric, title)
            elif chart_type == "bar":
                fig = self._create_bar_chart(df, metric, title)
            elif chart_type == "pie":
                fig = self._create_pie_chart(df, metric, title)
            elif chart_type == "area":
                fig = self._create_area_chart(df, metric, title)
            else:
                fig = self._create_line_chart(df, metric, title)
            
            # Exportar a imagen
            filename = f"{metric}_{chart_type}_{uuid.uuid4().hex[:8]}.png"
            filepath = self.output_dir / filename
            
            fig.write_image(str(filepath), width=1200, height=600, scale=2)
            
            logger.info(f"✅ Gráfico generado: {filepath}")
            
            return str(filepath)
        
        except Exception as e:
            logger.error(f"❌ Error generando gráfico: {str(e)}")
            raise
    
    async def generate_generation_chart(self) -> str:
        """
        Gráfico específico de generación eléctrica
        """
        return await self.generate_chart(
            metric="Gene",
            chart_type="area",
            period="7d",
            title="Generación Eléctrica - Últimos 7 Días"
        )
    
    async def generate_price_chart(self) -> str:
        """
        Gráfico de evolución de precios
        """
        return await self.generate_chart(
            metric="PrecioBolsa",
            chart_type="line",
            period="30d",
            title="Precio de Bolsa - Último Mes"
        )
    
    async def generate_mix_chart(self) -> str:
        """
        Gráfico de mix energético (pie chart)
        """
        return await self.generate_chart(
            metric="Gene",
            chart_type="pie",
            period="1d",
            title="Mix Energético Actual"
        )
    
    def _create_line_chart(
        self,
        df: pd.DataFrame,
        metric: str,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        Crea gráfico de líneas
        """
        fig = go.Figure()
        
        # Si hay múltiples recursos, graficar cada uno
        if 'recurso' in df.columns and df['recurso'].nunique() > 1:
            for recurso in df['recurso'].unique():
                df_recurso = df[df['recurso'] == recurso].copy()
                df_recurso['fecha'] = pd.to_datetime(df_recurso['fecha'])
                df_recurso = df_recurso.sort_values('fecha')
                
                fig.add_trace(go.Scatter(
                    x=df_recurso['fecha'],
                    y=df_recurso['valor_gwh'],
                    mode='lines+markers',
                    name=recurso,
                    line=dict(width=3),
                    marker=dict(size=6)
                ))
        else:
            # Gráfico simple
            df['fecha'] = pd.to_datetime(df['fecha'])
            df = df.sort_values('fecha')
            
            fig.add_trace(go.Scatter(
                x=df['fecha'],
                y=df['valor_gwh'],
                mode='lines+markers',
                line=dict(width=3, color='#3b82f6'),
                marker=dict(size=6)
            ))
        
        # Configuración
        fig.update_layout(
            title={
                'text': title or f"Métrica: {metric}",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'color': '#1e293b'}
            },
            xaxis_title="Fecha",
            yaxis_title="GWh" if metric != "PrecioBolsa" else "$/kWh",
            template="plotly_white",
            font=dict(size=12),
            hovermode='x unified',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(l=80, r=40, t=80, b=60)
        )
        
        return fig
    
    def _create_bar_chart(
        self,
        df: pd.DataFrame,
        metric: str,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        Crea gráfico de barras
        """
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.sort_values('fecha')
        
        fig = go.Figure()
        
        if 'recurso' in df.columns and df['recurso'].nunique() > 1:
            for recurso in df['recurso'].unique():
                df_recurso = df[df['recurso'] == recurso]
                fig.add_trace(go.Bar(
                    x=df_recurso['fecha'],
                    y=df_recurso['valor_gwh'],
                    name=recurso
                ))
        else:
            fig.add_trace(go.Bar(
                x=df['fecha'],
                y=df['valor_gwh'],
                marker_color='#3b82f6'
            ))
        
        fig.update_layout(
            title={
                'text': title or f"Métrica: {metric}",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20}
            },
            xaxis_title="Fecha",
            yaxis_title="GWh",
            template="plotly_white",
            barmode='stack' if 'recurso' in df.columns else 'group'
        )
        
        return fig
    
    def _create_pie_chart(
        self,
        df: pd.DataFrame,
        metric: str,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        Crea gráfico de torta (pie chart)
        """
        # Agrupar por recurso
        if 'recurso' in df.columns:
            df_grouped = df.groupby('recurso')['valor_gwh'].sum().reset_index()
            df_grouped = df_grouped.sort_values('valor_gwh', ascending=False)
            
            fig = go.Figure(data=[go.Pie(
                labels=df_grouped['recurso'],
                values=df_grouped['valor_gwh'],
                hole=0.3,
                textinfo='label+percent',
                textfont_size=14,
                marker=dict(line=dict(color='white', width=2))
            )])
        else:
            # Si no hay recursos, agrupar por entidad
            if 'entidad' in df.columns:
                df_grouped = df.groupby('entidad')['valor_gwh'].sum().reset_index()
                fig = go.Figure(data=[go.Pie(
                    labels=df_grouped['entidad'],
                    values=df_grouped['valor_gwh'],
                    hole=0.3
                )])
            else:
                raise ValueError("No se puede crear pie chart sin campo 'recurso' o 'entidad'")
        
        fig.update_layout(
            title={
                'text': title or f"Mix Energético: {metric}",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20}
            },
            template="plotly_white",
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.02
            )
        )
        
        return fig
    
    def _create_area_chart(
        self,
        df: pd.DataFrame,
        metric: str,
        title: Optional[str] = None
    ) -> go.Figure:
        """
        Crea gráfico de área apilada
        """
        df['fecha'] = pd.to_datetime(df['fecha'])
        df = df.sort_values('fecha')
        
        fig = go.Figure()
        
        if 'recurso' in df.columns and df['recurso'].nunique() > 1:
            for recurso in df['recurso'].unique():
                df_recurso = df[df['recurso'] == recurso]
                fig.add_trace(go.Scatter(
                    x=df_recurso['fecha'],
                    y=df_recurso['valor_gwh'],
                    mode='lines',
                    name=recurso,
                    stackgroup='one',
                    line=dict(width=0.5),
                    fillcolor=None
                ))
        else:
            fig.add_trace(go.Scatter(
                x=df['fecha'],
                y=df['valor_gwh'],
                mode='lines',
                fill='tozeroy',
                line=dict(color='#3b82f6', width=2)
            ))
        
        fig.update_layout(
            title={
                'text': title or f"Métrica: {metric}",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20}
            },
            xaxis_title="Fecha",
            yaxis_title="GWh",
            template="plotly_white",
            hovermode='x unified'
        )
        
        return fig
    
    def _parse_period(self, period: str) -> int:
        """
        Convierte período a días
        """
        period = period.lower()
        
        if period.endswith('d'):
            return int(period[:-1])
        elif period.endswith('w'):
            return int(period[:-1]) * 7
        elif period.endswith('m'):
            return int(period[:-1]) * 30
        elif period.endswith('y'):
            return int(period[:-1]) * 365
        else:
            return 7  # Default
