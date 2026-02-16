# 🌐 Cómo Compartir la API con Otras Personas

**Tu IP del servidor:** `172.17.0.46`  
**Fecha:** 6 de febrero de 2026

---

## ✅ **PASO 1: VERIFICAR QUE LA API ESTÉ CORRIENDO**

```bash
# Debe estar corriendo con:
./api/start_dev.sh

# Verificar puerto 8000 activo
ss -tuln | grep 8000
```

---

## 🌐 **PASO 2: COMPARTIR URL CON OTROS (RED LOCAL)**

### **Para personas en la MISMA RED:**

Comparte estas URLs con tus compañeros:

```
📡 API Base:           http://172.17.0.46:8000
📚 Documentación:      http://172.17.0.46:8000/api/docs
📖 ReDoc:              http://172.17.0.46:8000/api/redoc
🔍 Verificar estado:   http://172.17.0.46:8000/health
```

### **Ejemplo de uso para otros:**

```bash
# Desde cualquier computador en la red
curl "http://172.17.0.46:8000/api/v1/generation/system"

# O abrir en navegador:
# http://172.17.0.46:8000/api/docs
```

---

## 🔥 **PASO 3: CONFIGURAR FIREWALL (SI ES NECESARIO)**

### **Opción A: UFW (Ubuntu/Debian)**

```bash
# Ver estado
sudo ufw status

# Permitir puerto 8000
sudo ufw allow 8000/tcp

# Verificar
sudo ufw status numbered
```

### **Opción B: firewalld (CentOS/RHEL)**

```bash
# Permitir puerto 8000
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload

# Verificar
sudo firewall-cmd --list-ports
```

### **Opción C: iptables**

```bash
# Permitir puerto 8000
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

---

## 🌍 **ACCESO DESDE INTERNET (OPCIONAL)**

### **Método 1: ngrok (Túnel Rápido)**

```bash
# 1. Instalar ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
  sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
  sudo tee /etc/apt/sources.list.d/ngrok.list && \
  sudo apt update && sudo apt install ngrok

# 2. Autenticar (registrarse gratis en https://ngrok.com)
ngrok config add-authtoken TU_TOKEN_AQUI

# 3. Exponer API
ngrok http 8000
```

**Resultado:**
```
🌐 URL Pública: https://abc-123-def.ngrok-free.app

Ahora CUALQUIER PERSONA puede acceder:
https://abc-123-def.ngrok-free.app/api/docs
```

**Características ngrok:**
- ✅ Gratis para uso básico
- ✅ HTTPS automático
- ✅ URL pública instantánea
- ⚠️ URL temporal (cambia cada vez que reinicias)
- ⚠️ Límite de conexiones en plan gratuito

### **Método 2: Cloudflare Tunnel**

```bash
# 1. Instalar cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# 2. Autenticar
cloudflared tunnel login

# 3. Crear túnel
cloudflared tunnel create api-mme

# 4. Configurar
cloudflared tunnel route dns api-mme api.tudominio.com

# 5. Ejecutar
cloudflared tunnel run api-mme
```

---

## 📱 **EJEMPLOS DE USO PARA USUARIOS**

### **Desde JavaScript (Web)**

```html
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard Energía</title>
</head>
<body>
    <div id="data"></div>
    
    <script>
        // Cambiar IP según tu servidor
        const API_URL = 'http://172.17.0.46:8000';
        
        fetch(`${API_URL}/api/v1/generation/system`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('data').innerHTML = 
                    `<pre>${JSON.stringify(data, null, 2)}</pre>`;
            });
    </script>
</body>
</html>
```

### **Desde Python**

```python
import requests

# Cambiar IP según tu servidor
API_URL = 'http://172.17.0.46:8000'

# Obtener datos
response = requests.get(f'{API_URL}/api/v1/generation/system')
data = response.json()

print(f"Total puntos: {data['total_points']}")
print(f"Fecha inicio: {data['start_date']}")
print(f"Fecha fin: {data['end_date']}")
```

### **Desde Excel/Power BI**

```
1. Datos → Obtener datos → Desde Web
2. URL: http://172.17.0.46:8000/api/v1/generation/system
3. Aceptar
4. Power Query Editor → Expandir columnas
5. Cerrar y cargar
```

### **Desde Postman**

```
1. New Request → GET
2. URL: http://172.17.0.46:8000/api/v1/generation/system
3. Send
4. Ver respuesta JSON
```

---

## 🔐 **SEGURIDAD (IMPORTANTE)**

### **Para Producción:**

```bash
# 1. Habilitar autenticación API Key
export API_KEY_ENABLED=true
export API_KEY="tu-clave-super-secreta-aqui"

# 2. Cambiar a modo producción
export DASH_ENV=production

# 3. Usar HTTPS (SSL/TLS)
# Configurar con nginx + certbot

# 4. Rate limiting estricto
# Ya está configurado en FastAPI

# 5. Logs de auditoría
# Ver logs/api.log
```

### **Generar API Key segura:**

```bash
# Generar clave aleatoria
openssl rand -hex 32

# Resultado: 4f8a2e...3d9c1b
```

---

## 📊 **MONITOREO DE ACCESOS**

### **Ver conexiones en tiempo real:**

```bash
# Ver logs de API
tail -f /home/admonctrlxm/server/logs/api.log

# Ver conexiones TCP
ss -tn state established '( dport = :8000 or sport = :8000 )'

# Contar requests
tail -f logs/api.log | grep "GET /api/" | wc -l
```

---

## 🎯 **ESCENARIOS COMUNES**

### **Escenario 1: Equipo de Desarrollo (5-10 personas)**

```
✅ Usar red local (172.17.0.46:8000)
✅ Sin autenticación en desarrollo
✅ Documentación habilitada
```

### **Escenario 2: Demo para Cliente Externo**

```
✅ Usar ngrok para túnel temporal
✅ Compartir URL pública: https://xxx.ngrok.io
✅ Habilitar autenticación API Key
```

### **Escenario 3: Producción Ministerio**

```
✅ Dominio: api.mme.gov.co
✅ HTTPS con certificado SSL
✅ Autenticación OAuth2 + API Key
✅ Rate limiting: 1000 req/min
✅ Logs de auditoría
✅ Monitoreo 24/7
```

---

## ⚡ **RESUMEN RÁPIDO**

### **Para Red Local (AHORA):**

1. **Verificar IP del servidor:**
   ```bash
   hostname -I | awk '{print $1}'
   # Resultado: 172.17.0.46
   ```

2. **Abrir firewall (si es necesario):**
   ```bash
   sudo ufw allow 8000/tcp
   ```

3. **Compartir URL:**
   ```
   http://172.17.0.46:8000/api/docs
   ```

4. **LISTO** ✅ - Otros pueden acceder desde su navegador

### **Para Internet (OPCIONAL):**

1. **Instalar ngrok:**
   ```bash
   # Registrarse en ngrok.com (gratis)
   # Copiar token de autenticación
   ```

2. **Ejecutar:**
   ```bash
   ngrok http 8000
   ```

3. **Compartir URL pública:**
   ```
   https://abc-123.ngrok-free.app/api/docs
   ```

---

## 🆘 **PROBLEMAS COMUNES**

### **"No puedo acceder desde otra computadora"**

```bash
# 1. Verificar que API corra con 0.0.0.0 (no 127.0.0.1)
# El script start_dev.sh ya usa --host 0.0.0.0 ✅

# 2. Verificar firewall
sudo ufw status
sudo ufw allow 8000/tcp

# 3. Verificar que estén en la misma red
ping 172.17.0.46

# 4. Ver si puerto está escuchando
netstat -tuln | grep 8000
```

### **"Dice 'Connection refused'"**

```bash
# Verificar que API esté corriendo
ps aux | grep uvicorn

# Reiniciar API
pkill -f uvicorn
./api/start_dev.sh
```

### **"ngrok dice 'ERR_NGROK_108'"**

```bash
# Actualizar ngrok
ngrok update

# Verificar autenticación
ngrok config check
```

---

## 📞 **SOPORTE**

Para más ayuda:

1. **Documentación API:** http://172.17.0.46:8000/api/docs
2. **Logs del servidor:** `/home/admonctrlxm/server/logs/api.log`
3. **Configuración:** `/home/admonctrlxm/server/core/config.py`

---

**Generado:** 6 de febrero de 2026  
**Servidor:** 172.17.0.46:8000  
**Estado:** ✅ Operacional
