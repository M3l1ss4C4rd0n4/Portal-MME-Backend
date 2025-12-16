# Plan de Seguridad y Auditoría - SIEA

## 🎯 Objetivo

Garantizar que el Sistema Integral de Inteligencia Energética y Asistencia Ministerial (SIEA) cumpla con:
- **Ley 1581/2012** (Protección de Datos Personales)
- **Ley 1273/2009** (Delitos informáticos)
- **ISO 27001** (Gestión de Seguridad de la Información)
- **OWASP Top 10** (Vulnerabilidades web)
- **CIS Benchmarks** (Hardening de servidores)

---

## 🔒 CHECKLIST DE SEGURIDAD POR CAPA

### 1. Seguridad de Infraestructura

#### 1.1 Firewall y Perímetro

**Configuración iptables:**
```bash
# Política por defecto: denegar todo
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Permitir loopback
iptables -A INPUT -i lo -j ACCEPT

# Permitir HTTPS (443) solo desde IPs autorizadas
iptables -A INPUT -p tcp --dport 443 -s 200.21.45.0/24 -j ACCEPT  # Red MinMinas
iptables -A INPUT -p tcp --dport 443 -s 181.129.0.0/16 -j ACCEPT  # Meta (WhatsApp)

# Permitir SSH solo desde IP admin
iptables -A INPUT -p tcp --dport 22 -s 200.21.45.10 -j ACCEPT

# Bloquear todo lo demás
iptables -A INPUT -j LOG --log-prefix "FIREWALL_BLOCKED: "
iptables -A INPUT -j DROP

# Guardar reglas
iptables-save > /etc/iptables/rules.v4
```

**Checklist Firewall:**
- [ ] Solo puertos 443 (HTTPS) y 22 (SSH admin) abiertos
- [ ] SSH con autenticación por llave (no password)
- [ ] Fail2ban activo (bloqueo tras 3 intentos fallidos)
- [ ] Logs de firewall enviados a SIEM
- [ ] IP whitelist actualizada mensualmente

#### 1.2 WAF (Web Application Firewall)

**Opción: Cloudflare (recomendado)**

Configuración:
1. DNS apuntando a Cloudflare
2. Activar:
   - ✅ DDoS Protection (automático)
   - ✅ Rate Limiting: 100 req/min por IP
   - ✅ Bot Fight Mode
   - ✅ WAF Managed Rules (OWASP Core)

**Reglas custom:**
```javascript
// Bloquear requests sin User-Agent
(not http.user_agent contains "Mozilla") and (not http.user_agent contains "curl")

// Bloquear SQL injection patterns
(http.request.uri.query contains "UNION SELECT") or 
(http.request.uri.query contains "DROP TABLE")
```

**Checklist WAF:**
- [ ] OWASP ModSecurity Core Rules activas
- [ ] Rate limiting: 100 req/min/IP
- [ ] Challenge para tráfico sospechoso
- [ ] Logs de WAF analizados semanalmente

#### 1.3 TLS/SSL

**Certificado Let's Encrypt con renovación automática:**
```bash
# Instalar certbot
sudo apt install certbot python3-certbot-nginx

# Obtener certificado
sudo certbot --nginx -d siea.minminas.gov.co

# Verificar renovación automática
sudo systemctl status certbot.timer

# Test renovación manual
sudo certbot renew --dry-run
```

**Configuración NGINX:**
```nginx
# /etc/nginx/sites-available/siea

server {
    listen 443 ssl http2;
    server_name siea.minminas.gov.co;

    # Certificados
    ssl_certificate /etc/letsencrypt/live/siea.minminas.gov.co/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/siea.minminas.gov.co/privkey.pem;

    # TLS 1.3 únicamente
    ssl_protocols TLSv1.3;
    ssl_prefer_server_ciphers off;

    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirigir HTTP a HTTPS
server {
    listen 80;
    server_name siea.minminas.gov.co;
    return 301 https://$host$request_uri;
}
```

**Checklist TLS:**
- [ ] Solo TLS 1.3 habilitado
- [ ] Certificado válido (expira en > 30 días)
- [ ] HSTS header activo
- [ ] Security headers (X-Frame-Options, CSP, etc.)
- [ ] Test con SSL Labs: A+ rating
- [ ] Renovación automática funcionando

---

### 2. Seguridad de Aplicaciones

#### 2.1 Autenticación y Autorización

**OAuth2 + JWT con FastAPI:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta

SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # En KMS
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# RBAC
def require_role(required_role: str):
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in ["admin", required_role]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# Endpoint protegido
@app.get("/api/admin/users")
async def list_users(user: dict = Depends(require_role("admin"))):
    # Solo admins pueden ver lista de usuarios
    return {"users": [...]}
```

**Integración Azure AD (SSO):**
```python
# Para funcionarios MinMinas con cuenta @minminas.gov.co
from msal import ConfidentialClientApplication

app = ConfidentialClientApplication(
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_credential=os.getenv("AZURE_CLIENT_SECRET"),
    authority=f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID')}"
)

# Flujo de login
@app.get("/login")
async def login():
    auth_url = app.get_authorization_request_url(
        scopes=["User.Read"],
        redirect_uri="https://siea.minminas.gov.co/callback"
    )
    return RedirectResponse(auth_url)
```

**Checklist Autenticación:**
- [ ] JWT con expiración de 30 minutos
- [ ] Refresh tokens con expiración de 7 días
- [ ] SECRET_KEY almacenada en KMS/Key Vault
- [ ] MFA obligatorio para admins (TOTP)
- [ ] SSO con Azure AD para funcionarios
- [ ] Logs de todos los logins exitosos y fallidos
- [ ] Bloqueo tras 3 intentos fallidos (15 min)

#### 2.2 Protección contra Vulnerabilidades OWASP

**A01:2021 – Broken Access Control**
```python
# NUNCA confiar en IDs de URL sin validación
@app.get("/api/reports/{report_id}")
async def get_report(report_id: int, user: dict = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    
    # Validar que el usuario tiene acceso
    if report.owner_id != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    
    return report
```

**A02:2021 – Cryptographic Failures**
```python
# Encriptar datos sensibles
from cryptography.fernet import Fernet

# Key en KMS
cipher_suite = Fernet(os.getenv("ENCRYPTION_KEY"))

# Guardar
encrypted_data = cipher_suite.encrypt(sensitive_data.encode())
db.save(encrypted_data)

# Leer
decrypted_data = cipher_suite.decrypt(encrypted_data).decode()
```

**A03:2021 – Injection (SQL Injection)**
```python
# SIEMPRE usar ORM parametrizado
# ❌ MAL (vulnerable)
query = f"SELECT * FROM users WHERE email = '{email}'"

# ✅ BIEN (seguro)
user = db.query(User).filter(User.email == email).first()
```

**A05:2021 – Security Misconfiguration**
```python
# Desactivar debug en producción
app = FastAPI(debug=False)

# No exponer información sensible en errores
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    # NO mostrar stack trace en producción
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
```

**A07:2021 – Identification and Authentication Failures**
```python
# Passwords hasheados con bcrypt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Guardar
hashed_password = pwd_context.hash(plain_password)

# Verificar
if not pwd_context.verify(plain_password, hashed_password):
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

**Checklist OWASP:**
- [ ] Sin SQL injection (ORM con parámetros)
- [ ] Sin XSS (escape de HTML)
- [ ] Sin CSRF (tokens en formularios)
- [ ] Sin exposición de secrets en código
- [ ] Validación de inputs (Pydantic schemas)
- [ ] Rate limiting por endpoint
- [ ] Logs de todas las excepciones

#### 2.3 Seguridad de Dependencias

**Escaneo automático con Snyk:**
```bash
# Instalar Snyk CLI
npm install -g snyk

# Autenticarse
snyk auth

# Escanear requirements.txt
snyk test --file=requirements.txt

# Integración en CI/CD
# .github/workflows/security.yml
- name: Run Snyk
  run: snyk test --severity-threshold=high
```

**Trivy para imágenes Docker:**
```bash
# Escanear imagen local
trivy image siea-backend:latest

# Escanear en pipeline
docker build -t siea-backend:latest .
trivy image --exit-code 1 --severity CRITICAL,HIGH siea-backend:latest
```

**Checklist Dependencias:**
- [ ] Snyk scan semanal
- [ ] Trivy scan en cada build
- [ ] Renovate Bot para actualizaciones automáticas
- [ ] Sin dependencias con vulnerabilidades críticas
- [ ] Pin de versiones en requirements.txt

---

### 3. Seguridad de Datos

#### 3.1 Encriptación en Reposo

**PostgreSQL con TLS:**
```bash
# postgresql.conf
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file = '/etc/ssl/private/server.key'
ssl_ca_file = '/etc/ssl/certs/ca.crt'

# pg_hba.conf (forzar TLS)
hostssl all all 0.0.0.0/0 md5
```

**Encriptación de columnas sensibles:**
```python
# Para datos extremadamente sensibles
from sqlalchemy_utils import EncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesEngine

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String)
    
    # Encriptar columna
    national_id = Column(
        EncryptedType(String, os.getenv("COLUMN_ENCRYPTION_KEY"), AesEngine, "pkcs5")
    )
```

**Checklist Encriptación:**
- [ ] PostgreSQL con TLS 1.3
- [ ] Backups encriptados (AES-256)
- [ ] Columnas sensibles con encriptación a nivel aplicación
- [ ] Keys en KMS (AWS KMS / Azure Key Vault)
- [ ] Rotación de keys cada 90 días

#### 3.2 Backups Seguros

**Script de backup encriptado:**
```bash
#!/bin/bash
# /opt/siea/scripts/backup_encrypted.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
DB_NAME="siea"
GPG_RECIPIENT="backup@minminas.gov.co"

# Dump
pg_dump -h localhost -U siea_user $DB_NAME | gzip > /tmp/backup_$TIMESTAMP.sql.gz

# Encriptar con GPG
gpg --encrypt --recipient $GPG_RECIPIENT /tmp/backup_$TIMESTAMP.sql.gz

# Mover a S3 (con encriptación server-side)
aws s3 cp /tmp/backup_$TIMESTAMP.sql.gz.gpg s3://minminas-backups/siea/ --sse AES256

# Limpiar
rm /tmp/backup_$TIMESTAMP.sql.gz*

# Retener solo últimos 90 días
aws s3 ls s3://minminas-backups/siea/ | awk '{print $4}' | head -n -90 | xargs -I {} aws s3 rm s3://minminas-backups/siea/{}
```

**Checklist Backups:**
- [ ] Backups diarios (automáticos a las 2 AM)
- [ ] Encriptados con GPG o AES-256
- [ ] Almacenados en S3/Azure Blob (fuera del servidor)
- [ ] Retención: 90 días mínimo
- [ ] Test de restore mensual

---

### 4. Monitoreo y Auditoría

#### 4.1 Logging Centralizado (ELK Stack)

**Filebeat para enviar logs:**
```yaml
# /etc/filebeat/filebeat.yml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/siea/*.log
      - /var/log/nginx/access.log
      - /var/log/auth.log
    fields:
      service: siea
      environment: production

output.elasticsearch:
  hosts: ["https://elk.minminas.gov.co:9200"]
  username: "filebeat"
  password: "${FILEBEAT_PASSWORD}"
  ssl.verification_mode: full
```

**Índices en Elasticsearch:**
```bash
# Crear índice con retención de 7 años
PUT /siea-audit-logs
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 2
  }
}

# ILM policy (7 años)
PUT _ilm/policy/siea-7year-retention
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_size": "50gb",
            "max_age": "30d"
          }
        }
      },
      "delete": {
        "min_age": "2555d",  # 7 años
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

**Checklist Logging:**
- [ ] Logs centralizados en ELK Stack
- [ ] Retención de 7 años (requisito legal)
- [ ] Logs de: accesos, queries, predicciones, errores
- [ ] Dashboard Kibana para análisis
- [ ] Alertas automáticas (más de 10 errores/min)

#### 4.2 Auditoría de Accesos

**Tabla de auditoría:**
```sql
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(50) NOT NULL,  -- 'login', 'query', 'predict', 'export'
    resource VARCHAR(255),  -- tabla, endpoint, archivo
    ip_address INET NOT NULL,
    user_agent TEXT,
    status VARCHAR(20),  -- 'success', 'denied', 'error'
    details JSONB,  -- parámetros adicionales
    INDEX idx_user_timestamp (user_id, timestamp),
    INDEX idx_action (action)
);

-- Retención de 7 años (particionamiento)
CREATE TABLE audit_log_2025 PARTITION OF audit_log
FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
```

**Middleware de auditoría:**
```python
from fastapi import Request
import time

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Capturar info
    user = getattr(request.state, "user", None)
    ip = request.client.host
    
    # Ejecutar request
    response = await call_next(request)
    
    # Registrar en auditoría
    await db.execute(
        """
        INSERT INTO audit_log (user_id, action, resource, ip_address, status, details)
        VALUES (:user_id, :action, :resource, :ip, :status, :details)
        """,
        {
            "user_id": user.id if user else None,
            "action": request.method,
            "resource": request.url.path,
            "ip": ip,
            "status": response.status_code,
            "details": {"duration_ms": int((time.time() - start_time) * 1000)}
        }
    )
    
    return response
```

**Checklist Auditoría:**
- [ ] Tabla audit_log con retención 7 años
- [ ] Logs de: logins, queries, predicciones, exports
- [ ] IP, user-agent, timestamp en cada registro
- [ ] Dashboard semanal revisado por TIC
- [ ] Alertas automáticas para:
  - Login fuera de horario (22:00-06:00)
  - Consulta de > 100K registros
  - 3+ logins fallidos

---

### 5. Pentesting y Cumplimiento

#### 5.1 Pentest Checklist

**Scope del pentest:**
- [ ] API endpoints (autenticación, autorización, injection)
- [ ] Dashboard (XSS, CSRF, clickjacking)
- [ ] Infraestructura (puertos abiertos, servicios expuestos)
- [ ] WhatsApp webhook (HMAC bypass, replay attacks)

**Herramientas:**
```bash
# Escaneo de puertos
nmap -sV -sC siea.minminas.gov.co

# Escaneo de vulnerabilidades web
nikto -h https://siea.minminas.gov.co

# Test de SQL injection
sqlmap -u "https://siea.minminas.gov.co/api/reports?id=1"

# Fuzzing de API
ffuf -u https://siea.minminas.gov.co/api/FUZZ -w wordlist.txt
```

**Frecuencia:**
- [ ] Pentest completo: Semestral
- [ ] Escaneo automático: Semanal (Snyk + Trivy)
- [ ] Revisión de código: En cada PR (SonarQube)

#### 5.2 Compliance Checklist

**Ley 1581/2012 (Protección de Datos):**
- [ ] DPIA completada y aprobada
- [ ] Convenios de datos firmados con distribuidoras
- [ ] NDAs firmados por personal con acceso
- [ ] Política de retención (7 años) implementada
- [ ] Derechos ARCO (acceso, rectificación, cancelación, oposición) habilitados
- [ ] Registro de tratamiento de datos actualizado

**ISO 27001:**
- [ ] Política de seguridad documentada
- [ ] Matriz de riesgos actualizada trimestralmente
- [ ] Inventario de activos (servidores, bases de datos, APIs)
- [ ] Plan de continuidad del negocio (BCP)
- [ ] Tests de disaster recovery semestrales

**OWASP Top 10:**
- [ ] Sin vulnerabilidades críticas o altas
- [ ] SonarQube scan en cada commit
- [ ] Security headers configurados (HSTS, CSP, etc.)
- [ ] Validación de inputs con Pydantic
- [ ] Rate limiting activo

---

## 📅 Calendario de Auditorías

| Actividad | Frecuencia | Responsable | Última Ejecución |
|-----------|-----------|-------------|------------------|
| Revisión logs de acceso | Semanal | TIC | - |
| Escaneo de vulnerabilidades (Snyk) | Semanal | DevOps | - |
| Actualización de dependencias | Mensual | DevOps | - |
| Test de backups (restore) | Mensual | TIC | - |
| Revisión de matriz de riesgos | Trimestral | CISO | - |
| Pentest completo | Semestral | Externo | - |
| Auditoría de cumplimiento (ISO 27001) | Anual | Externo | - |

---

## 🚨 Plan de Respuesta a Incidentes

### Clasificación de Incidentes

| Severidad | Ejemplos | Tiempo de Respuesta |
|-----------|----------|---------------------|
| **Crítico** | Brecha de datos, ransomware, caída total | < 15 minutos |
| **Alto** | Intento de intrusión, DoS, vulnerabilidad crítica | < 1 hora |
| **Medio** | Errores recurrentes, performance degradado | < 4 horas |
| **Bajo** | Logs anómalos, configuración incorrecta | < 24 horas |

### Flujo de Respuesta

1. **Detección** → Alerta automática (Prometheus/ELK) o reporte manual
2. **Contención** → Aislar sistema afectado (firewall, shutdown temporal)
3. **Análisis** → Revisar logs, identificar causa raíz
4. **Erradicación** → Eliminar amenaza (patch, rollback, cambio de keys)
5. **Recuperación** → Restaurar servicio (from backup si es necesario)
6. **Post-Mortem** → Documentar incidente, lecciones aprendidas

### Contactos de Emergencia

- **TIC MinMinas:** [correo@minminas.gov.co] - 601 XXX XXXX
- **CSIRT Colombia:** csirt@policia.gov.co - 018000 916 600
- **Meta Support (WhatsApp):** business.facebook.com/help

---

**Última actualización:** 2025-12-02  
**Responsable:** [Líder Seguridad SIEA]  
**Próxima revisión:** 2025-03-02
