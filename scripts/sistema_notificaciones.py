"""
Sistema de Notificaciones para Alertas Energéticas
Módulo centralizado para enviar notificaciones vía EMAIL y WhatsApp

Autor: Portal Energético MME
Fecha: 9 de Febrero de 2026
"""

import smtplib
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional
import logging
import psycopg2
from infrastructure.database.connection import PostgreSQLConnectionManager

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÓN DE EMAIL
# ============================================================================

EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',  # Por defecto Gmail, configurar según servidor MME
    'smtp_port': 587,
    'smtp_user': 'portal.energetico@minenergia.gov.co',  # Configurar email corporativo
    'smtp_password': '',  # ⚠️ CONFIGURAR variable de entorno: SMTP_PASSWORD
    'from_name': 'Portal Energético MME - Sistema de Alertas',
    'from_email': 'alertas@portal.minenergia.gov.co'
}

# ============================================================================
# CONFIGURACIÓN DE WHATSAPP BOT
# ============================================================================

WHATSAPP_CONFIG = {
    'bot_url': 'http://localhost:8001/api/send-alert',  # URL del bot de Oscar
    'bot_api_key': '',  # ⚠️ CONFIGURAR si el bot requiere autenticación
    'timeout': 10  # segundos
}

# ============================================================================
# CLASE: NotificationService
# ============================================================================

class NotificationService:
    """Servicio centralizado de notificaciones"""
    
    def __init__(self):
        """Inicializa el servicio de notificaciones"""
        self.db_manager = PostgreSQLConnectionManager()
        self.conn = None
        self._connect_db()
    
    def _connect_db(self):
        """Establece conexión con PostgreSQL"""
        try:
            conn_params = {
                'host': self.db_manager.host,
                'port': self.db_manager.port,
                'database': self.db_manager.database,
                'user': self.db_manager.user
            }
            if self.db_manager.password:
                conn_params['password'] = self.db_manager.password
            
            self.conn = psycopg2.connect(**conn_params)
            logger.info("✅ Conexión a PostgreSQL establecida")
        except Exception as e:
            logger.error(f"❌ Error conectando a PostgreSQL: {e}")
            self.conn = None
    
    def get_destinatarios(self, tipo: str, recibir_criticas: bool = True) -> List[Dict]:
        """
        Obtiene destinatarios configurados para un tipo de notificación
        
        Args:
            tipo: 'EMAIL' o 'WHATSAPP'
            recibir_criticas: Si True, solo retorna destinatarios que reciben alertas críticas
        
        Returns:
            Lista de diccionarios con info de destinatarios
        """
        try:
            cursor = self.conn.cursor()
            
            query = """
            SELECT destinatario, nombre, cargo, recibir_alertas_criticas
            FROM configuracion_notificaciones
            WHERE tipo = %s 
              AND activo = TRUE
            """
            
            if recibir_criticas:
                query += " AND recibir_alertas_criticas = TRUE"
            
            cursor.execute(query, (tipo,))
            rows = cursor.fetchall()
            cursor.close()
            
            destinatarios = []
            for row in rows:
                destinatarios.append({
                    'destinatario': row[0],
                    'nombre': row[1],
                    'cargo': row[2],
                    'recibe_criticas': row[3]
                })
            
            return destinatarios
        
        except Exception as e:
            logger.error(f"❌ Error obteniendo destinatarios: {e}")
            return []
    
    def enviar_email(
        self,
        destinatarios: List[str],
        asunto: str,
        cuerpo_html: str,
        severidad: str = 'NORMAL'
    ) -> Dict:
        """
        Envía email a destinatarios
        
        Args:
            destinatarios: Lista de emails
            asunto: Asunto del email
            cuerpo_html: Cuerpo en HTML
            severidad: NORMAL, ALERTA, CRÍTICO
        
        Returns:
            Dict con 'success', 'enviados', 'fallidos', 'error'
        """
        try:
            import os
            smtp_password = os.environ.get('SMTP_PASSWORD', EMAIL_CONFIG['smtp_password'])
            
            if not smtp_password:
                logger.warning("⚠️ SMTP_PASSWORD no configurada. Email no enviado.")
                return {
                    'success': False,
                    'enviados': [],
                    'fallidos': destinatarios,
                    'error': 'SMTP_PASSWORD no configurada'
                }
            
            # Crear mensaje
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{EMAIL_CONFIG['from_name']} <{EMAIL_CONFIG['from_email']}>"
            msg['To'] = ', '.join(destinatarios)
            
            # Agregar emoji según severidad
            emoji = {
                'NORMAL': '✅',
                'ALERTA': '⚠️',
                'CRÍTICO': '🚨'
            }.get(severidad, '📊')
            
            msg['Subject'] = f"{emoji} {asunto}"
            
            # Adjuntar HTML
            html_part = MIMEText(cuerpo_html, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Enviar
            with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
                server.starttls()
                server.login(EMAIL_CONFIG['smtp_user'], smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email enviado a {len(destinatarios)} destinatarios")
            
            return {
                'success': True,
                'enviados': destinatarios,
                'fallidos': [],
                'error': None
            }
        
        except Exception as e:
            logger.error(f"❌ Error enviando email: {e}")
            return {
                'success': False,
                'enviados': [],
                'fallidos': destinatarios,
                'error': str(e)
            }
    
    def enviar_whatsapp(
        self,
        destinatarios: List[str],
        mensaje: str,
        severidad: str = 'NORMAL'
    ) -> Dict:
        """
        Envía mensaje de WhatsApp a destinatarios via bot de Oscar
        
        Args:
            destinatarios: Lista de números WhatsApp (+57...)
            mensaje: Texto del mensaje
            severidad: NORMAL, ALERTA, CRÍTICO
        
        Returns:
            Dict con 'success', 'enviados', 'fallidos', 'error'
        """
        try:
            # Agregar emoji según severidad
            emoji = {
                'NORMAL': '✅',
                'ALERTA': '⚠️',
                'CRÍTICO': '🚨'
            }.get(severidad, '📊')
            
            mensaje_formateado = f"{emoji} *ALERTA ENERGÉTICA - MME*\n\n{mensaje}"
            
            enviados = []
            fallidos = []
            
            for numero in destinatarios:
                try:
                    # Payload para el bot de Oscar
                    payload = {
                        'phone': numero,
                        'message': mensaje_formateado,
                        'type': 'alert',
                        'severity': severidad
                    }
                    
                    headers = {
                        'Content-Type': 'application/json'
                    }
                    
                    if WHATSAPP_CONFIG['bot_api_key']:
                        headers['Authorization'] = f"Bearer {WHATSAPP_CONFIG['bot_api_key']}"
                    
                    # Enviar request al bot
                    response = requests.post(
                        WHATSAPP_CONFIG['bot_url'],
                        json=payload,
                        headers=headers,
                        timeout=WHATSAPP_CONFIG['timeout']
                    )
                    
                    if response.status_code == 200:
                        enviados.append(numero)
                        logger.info(f"✅ WhatsApp enviado a {numero}")
                    else:
                        fallidos.append(numero)
                        logger.warning(f"⚠️ WhatsApp falló para {numero}: {response.status_code}")
                
                except Exception as e:
                    fallidos.append(numero)
                    logger.error(f"❌ Error enviando WhatsApp a {numero}: {e}")
            
            return {
                'success': len(enviados) > 0,
                'enviados': enviados,
                'fallidos': fallidos,
                'error': None if len(enviados) > 0 else 'Todos los envíos fallaron'
            }
        
        except Exception as e:
            logger.error(f"❌ Error general enviando WhatsApp: {e}")
            return {
                'success': False,
                'enviados': [],
                'fallidos': destinatarios,
                'error': str(e)
            }
    
    def generar_email_html_alerta(self, alerta: Dict) -> str:
        """
        Genera HTML para email de alerta
        
        Args:
            alerta: Dict con datos de la alerta del JSON
        
        Returns:
            String con HTML formateado
        """
        severidad = alerta.get('severidad', 'NORMAL')
        metrica = alerta.get('metrica', 'DESCONOCIDA')
        descripcion = alerta.get('descripcion', '')
        recomendacion = alerta.get('recomendacion', '')
        valor_promedio = alerta.get('valor_promedio', 0)
        
        # Color según severidad
        color_map = {
            'NORMAL': '#10b981',
            'ALERTA': '#f59e0b',
            'CRÍTICO': '#ef4444'
        }
        color = color_map.get(severidad, '#6b7280')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .metric-box {{ background-color: #f9fafb; border-left: 4px solid {color}; padding: 15px; margin: 20px 0; }}
                .metric-box h3 {{ margin-top: 0; color: {color}; }}
                .footer {{ background-color: #1f2937; color: white; padding: 15px; text-align: center; font-size: 12px; }}
                .btn {{ display: inline-block; background-color: {color}; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🇨🇴 ALERTA ENERGÉTICA - SECTOR NACIONAL</h1>
                    <p style="margin: 5px 0 0 0; font-size: 14px;">Ministerio de Minas y Energía</p>
                </div>
                
                <div class="content">
                    <h2 style="color: {color}; margin-top: 0;">SEVERIDAD: {severidad}</h2>
                    
                    <div class="metric-box">
                        <h3>📊 MÉTRICA: {metrica}</h3>
                        <p><strong>Valor promedio:</strong> {valor_promedio:.2f} GWh/día</p>
                        <p><strong>Descripción:</strong></p>
                        <p>{descripcion}</p>
                    </div>
                    
                    <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0;">
                        <h4 style="margin-top: 0; color: #92400e;">⚡ RECOMENDACIÓN:</h4>
                        <p style="margin-bottom: 0;">{recomendacion}</p>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                        <strong>Fecha de evaluación:</strong> {datetime.now().strftime('%d de %B de %Y, %H:%M')}
                    </p>
                    
                    <a href="https://portal.minenergia.gov.co/generacion?tab=predicciones" class="btn">
                        Ver Dashboard Completo
                    </a>
                </div>
                
                <div class="footer">
                    <p>Portal Energético del Ministerio de Minas y Energía</p>
                    <p>Sistema de Alertas Automáticas - Predicciones con Machine Learning</p>
                    <p style="margin-top: 10px; color: #9ca3af;">Este mensaje fue generado automáticamente. No responder.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def generar_mensaje_whatsapp_alerta(self, alerta: Dict) -> str:
        """
        Genera mensaje de texto para WhatsApp
        
        Args:
            alerta: Dict con datos de la alerta
        
        Returns:
            String con mensaje formateado para WhatsApp
        """
        severidad = alerta.get('severidad', 'NORMAL')
        metrica = alerta.get('metrica', 'DESCONOCIDA')
        descripcion = alerta.get('descripcion', '')
        recomendacion = alerta.get('recomendacion', '')
        valor_promedio = alerta.get('valor_promedio', 0)
        
        mensaje = f"""*ALERTA ENERGÉTICA - SECTOR NACIONAL*
_Ministerio de Minas y Energía_

🎯 *SEVERIDAD:* {severidad}
📊 *MÉTRICA:* {metrica}
📈 *VALOR:* {valor_promedio:.2f} GWh/día

📝 *SITUACIÓN:*
{descripcion}

⚡ *RECOMENDACIÓN:*
{recomendacion}

📅 *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}

🔗 Ver dashboard completo:
https://portal.minenergia.gov.co/generacion?tab=predicciones

_Sistema de Alertas Automáticas - Portal Energético MME_
"""
        
        return mensaje
    
    def close(self):
        """Cierra conexión a base de datos"""
        if self.conn:
            self.conn.close()
            logger.info("✅ Conexión a PostgreSQL cerrada")

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def notificar_alerta(
    alerta: Dict,
    enviar_email: bool = True,
    enviar_whatsapp: bool = True,
    solo_criticas: bool = True
) -> Dict:
    """
    Función helper para notificar una alerta
    
    Args:
        alerta: Dict con datos de la alerta (del JSON de alertas_energeticas.py)
        enviar_email: Si True, envía email
        enviar_whatsapp: Si True, envía WhatsApp
        solo_criticas: Si True, solo notifica alertas CRÍTICAS
    
    Returns:
        Dict con resultados de notificaciones
    """
    service = NotificationService()
    
    try:
        severidad = alerta.get('severidad', 'NORMAL')
        
        # Si solo_criticas=True, no enviar si no es crítica
        if solo_criticas and severidad != 'CRÍTICO':
            return {
                'email': {'success': False, 'message': 'No es crítica, omitida'},
                'whatsapp': {'success': False, 'message': 'No es crítica, omitida'}
            }
        
        resultado = {}
        
        # Enviar EMAIL
        if enviar_email:
            destinatarios_email = service.get_destinatarios('EMAIL', recibir_criticas=True)
            emails = [d['destinatario'] for d in destinatarios_email]
            
            if emails:
                html = service.generar_email_html_alerta(alerta)
                asunto = f"Alerta {severidad}: {alerta.get('metrica', 'DESCONOCIDA')}"
                resultado['email'] = service.enviar_email(emails, asunto, html, severidad)
            else:
                resultado['email'] = {'success': False, 'message': 'No hay destinatarios configurados'}
        
        # Enviar WHATSAPP
        if enviar_whatsapp:
            destinatarios_whatsapp = service.get_destinatarios('WHATSAPP', recibir_criticas=True)
            numeros = [d['destinatario'] for d in destinatarios_whatsapp]
            
            if numeros:
                mensaje = service.generar_mensaje_whatsapp_alerta(alerta)
                resultado['whatsapp'] = service.enviar_whatsapp(numeros, mensaje, severidad)
            else:
                resultado['whatsapp'] = {'success': False, 'message': 'No hay destinatarios configurados'}
        
        return resultado
    
    finally:
        service.close()

# ============================================================================
# MAIN (para testing)
# ============================================================================

if __name__ == "__main__":
    # Test de notificaciones
    alerta_test = {
        'severidad': 'CRÍTICO',
        'metrica': 'DEMANDA',
        'valor_promedio': 275.5,
        'descripcion': 'La demanda proyectada excede los umbrales críticos (>250 GWh/día). Riesgo de déficit energético.',
        'recomendacion': 'Activar generación térmica backup inmediatamente. Coordinar con XM. Considerar importaciones de emergencia.'
    }
    
    print("🧪 Test de sistema de notificaciones...")
    resultado = notificar_alerta(alerta_test, enviar_email=False, enviar_whatsapp=False, solo_criticas=False)
    print(json.dumps(resultado, indent=2))
    print("✅ Test completado")
