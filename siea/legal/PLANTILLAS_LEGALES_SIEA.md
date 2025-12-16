# PLANTILLAS LEGALES - SIEA

## Sistema Integral de Inteligencia Energética y Asistencia Ministerial

**Ministerio de Minas y Energía - Colombia**

---

## 📋 ÍNDICE

1. [DPIA - Evaluación de Impacto en Protección de Datos](#1-dpia)
2. [Convenio de Datos con Distribuidoras](#2-convenio-de-datos)
3. [NDA - Acuerdo de Confidencialidad](#3-nda)
4. [Política de Retención y Eliminación](#4-politica-retencion)
5. [Consentimiento Informado (si aplica)](#5-consentimiento-informado)

---

<a name="1-dpia"></a>
## 1. DPIA - EVALUACIÓN DE IMPACTO EN PROTECCIÓN DE DATOS

### Data Protection Impact Assessment (DPIA) - SIEA

**Fecha de evaluación:** [FECHA]  
**Responsable:** [Nombre Oficial de Protección de Datos]  
**Versión:** 1.0

---

### 1.1 DESCRIPCIÓN DEL TRATAMIENTO

**Nombre del sistema:** SIEA - Sistema Integral de Inteligencia Energética y Asistencia Ministerial

**Finalidad del tratamiento:**
- Análisis de datos del sector eléctrico colombiano
- Generación de modelos predictivos (demanda, precios, pérdidas)
- Asistencia conversacional a funcionarios del Ministerio
- Generación de reportes y alertas automáticas
- Monitoreo de indicadores del sector energético

**Base legal:**
- Ley 1581 de 2012 (Protección de Datos Personales)
- Decreto 1377 de 2013
- Ley 1712 de 2014 (Transparencia)
- Funciones misionales del Ministerio de Minas y Energía

---

### 1.2 DATOS PERSONALES TRATADOS

#### Datos que SÍ se procesan:
| Tipo de dato | Fuente | Finalidad | Nivel de agregación |
|--------------|--------|-----------|---------------------|
| NIU (Número Instalación Único) | SUI | Análisis de pérdidas por OR | **Hasheado** (SHA-256) |
| Consumo eléctrico por estrato | SUI | Modelos de demanda | **Agregado** (municipal/departamental) |
| Ubicación geográfica | SUI/XM | Mapas de riesgo | **Agregado** (municipio, NO dirección exacta) |
| Datos de facturación agregados | SUI | Análisis de pérdidas comerciales | **Agregado** (por OR/distribuidora) |

#### Datos que NO se procesan:
- ❌ Nombres completos de usuarios finales
- ❌ Cédulas de ciudadanía
- ❌ Direcciones exactas de usuarios
- ❌ Números de teléfono de usuarios
- ❌ Datos sensibles (salud, orientación sexual, etc.)

---

### 1.3 NECESIDAD Y PROPORCIONALIDAD

**¿Es necesario el tratamiento?**  
✅ SÍ. El análisis de datos del sector eléctrico es esencial para las funciones misionales del Ministerio (planeación, regulación, monitoreo).

**¿Es proporcional?**  
✅ SÍ. Solo se procesan datos agregados o anonimizados. No se almacenan datos personales identificables.

**¿Existen alternativas menos invasivas?**  
❌ NO. Los agregados y hash son el mínimo necesario para análisis técnicos válidos.

---

### 1.4 RIESGOS PARA LOS TITULARES

| Riesgo | Probabilidad | Impacto | Medida de Mitigación |
|--------|--------------|---------|----------------------|
| Re-identificación de usuarios a partir de NIU hasheado | BAJA | ALTO | Hash SHA-256 + salt único por OR. Sin almacenamiento de NIU plano. |
| Inferencia de consumo individual desde agregados | BAJA | MEDIO | K-anonymity (k≥5). Solo agregados municipales/departamentales. |
| Acceso no autorizado a base de datos | MEDIA | CRÍTICO | IAM least-privilege, MFA, cifrado at-rest (KMS), auditoría completa. |
| Fuga de datos en tránsito | BAJA | ALTO | TLS 1.3 obligatorio. Sin transmisión de datos fuera de canales seguros. |
| Uso indebido de datos por personal interno | BAJA | ALTO | NDA firmado. Acceso con roles. Log de auditoría 7 años. |

---

### 1.5 MEDIDAS DE PROTECCIÓN IMPLEMENTADAS

#### Técnicas
- ✅ **Anonimización**: K-anonymity (k≥5) + L-diversity
- ✅ **Hashing**: SHA-256 con salt para NIU
- ✅ **Cifrado at-rest**: KMS/Azure Key Vault
- ✅ **Cifrado in-transit**: TLS 1.3
- ✅ **Control de acceso**: IAM + MFA obligatorio
- ✅ **Auditoría**: Log completo de accesos y consultas (7 años)
- ✅ **Backup cifrado**: AES-256

#### Organizativas
- ✅ **NDA firmado** por todo el personal con acceso
- ✅ **Capacitación** en protección de datos (anual)
- ✅ **Revisión trimestral** de accesos y permisos
- ✅ **Oficial de Protección de Datos** designado
- ✅ **Plan de respuesta a incidentes** documentado

---

### 1.6 TRANSFERENCIAS INTERNACIONALES

**¿Se transfieren datos fuera de Colombia?**  
⚠️ **PARCIALMENTE**. 

- **OpenAI API** (Estados Unidos): Solo prompts agregados sin PII. Contrato DPA firmado.
- **WhatsApp Cloud API** (Meta, Estados Unidos): Solo mensajes institucionales sin datos sensibles.

**Garantías:**
- ✅ Cláusulas contractuales estándar (SCC)
- ✅ Data Processing Agreement (DPA) con OpenAI
- ✅ Revisión legal de términos de servicio WhatsApp Business
- ✅ NO se envían datos personales identificables a APIs externas

---

### 1.7 DERECHOS DE LOS TITULARES

Los titulares de datos (usuarios del SUI) conservan sus derechos ARCO:
- **Acceso**: Solicitar información sobre datos tratados
- **Rectificación**: Corregir datos inexactos
- **Cancelación**: Solicitar eliminación (sujeto a retención legal)
- **Oposición**: Oponerse al tratamiento (si aplica)

**Procedimiento:**
1. Solicitud por escrito a: datospersonales@minenergia.gov.co
2. Respuesta en máximo 15 días hábiles
3. Escalamiento a SIC si no hay respuesta satisfactoria

---

### 1.8 RETENCIÓN Y ELIMINACIÓN

| Tipo de dato | Retención | Justificación legal | Método eliminación |
|--------------|-----------|---------------------|-------------------|
| Datos agregados operacionales | 7 años | Archivo general de la nación | Eliminación segura NIST SP 800-88 |
| Logs de auditoría | 7 años | Cumplimiento normativo | Eliminación segura + certificado |
| Modelos ML | Indefinido (versionado) | Continuidad operativa | Depuración de versiones antiguas cada 5 años |
| Backups | 1 año (mensual), 3 meses (diario) | Recuperación ante desastres | Eliminación segura + log |

---

### 1.9 CONCLUSIONES Y RECOMENDACIONES

**Conclusión general:**  
El tratamiento de datos del sistema SIEA cumple con los principios de la Ley 1581 de 2012:
- ✅ Legalidad
- ✅ Finalidad
- ✅ Libertad
- ✅ Veracidad
- ✅ Transparencia
- ✅ Acceso y circulación restringida
- ✅ Seguridad
- ✅ Confidencialidad

**Riesgos residuales:** BAJOS (después de implementar todas las medidas de mitigación)

**Recomendaciones:**
1. Realizar auditoría de protección de datos cada 6 meses
2. Actualizar DPIA si hay cambios significativos en el tratamiento
3. Revisar contratos DPA con proveedores externos anualmente
4. Capacitar al personal en protección de datos (anual)
5. Implementar Privacy by Design en futuras ampliaciones

---

### 1.10 APROBACIONES

**Elaborado por:**  
[Nombre] - [Cargo]  
Fecha: _______________

**Revisado por:**  
[Nombre Oficial de Protección de Datos]  
Fecha: _______________

**Aprobado por:**  
[Nombre Director/Secretario General]  
Fecha: _______________

---

<a name="2-convenio-de-datos"></a>
## 2. CONVENIO DE DATOS CON DISTRIBUIDORAS

### CONVENIO DE COLABORACIÓN PARA INTERCAMBIO DE INFORMACIÓN DEL SECTOR ELÉCTRICO

**ENTRE:**

**MINISTERIO DE MINAS Y ENERGÍA**, entidad del orden nacional, representado por [NOMBRE], identificado con C.C. [NÚMERO], en calidad de [CARGO], en adelante **"EL MINISTERIO"**

**Y**

**[NOMBRE DISTRIBUIDORA]**, sociedad comercial identificada con NIT [NÚMERO], representada por [NOMBRE], identificado con C.C. [NÚMERO], en calidad de [CARGO], en adelante **"LA DISTRIBUIDORA"**

---

### CLÁUSULAS

**PRIMERA - OBJETO:**  
El presente convenio tiene por objeto establecer los términos y condiciones para el intercambio de información técnica y operativa del sector eléctrico, necesaria para el desarrollo del Sistema Integral de Inteligencia Energética y Asistencia Ministerial (SIEA), en cumplimiento de las funciones misionales del Ministerio.

**SEGUNDA - OBLIGACIONES DEL MINISTERIO:**
1. Utilizar la información exclusivamente para fines institucionales relacionados con planeación, regulación y monitoreo del sector eléctrico
2. Implementar medidas de seguridad técnicas y organizativas para proteger la información
3. Garantizar que solo personal autorizado y bajo NDA acceda a los datos
4. Anonimizar/agregar datos personales antes de su procesamiento
5. No ceder ni transferir la información a terceros sin autorización escrita de LA DISTRIBUIDORA
6. Destruir la información al finalizar la vigencia del convenio, previa certificación

**TERCERA - OBLIGACIONES DE LA DISTRIBUIDORA:**
1. Suministrar la información en los formatos y periodicidad acordados (Anexo 1)
2. Garantizar la veracidad, exactitud y actualidad de la información
3. Notificar al MINISTERIO cualquier error o inconsistencia detectada
4. Designar un punto de contacto técnico para coordinación

**CUARTA - INFORMACIÓN OBJETO DEL CONVENIO:**  
(Ver Anexo 1 - Especificación Técnica)
- Pérdidas técnicas y comerciales mensuales por OR
- Consumo agregado por estrato y municipio
- Índices de calidad del servicio (DES, FES)
- Infraestructura de red (longitud, transformadores)
- **NOTA:** No se incluyen datos personales identificables de usuarios finales

**QUINTA - PROTECCIÓN DE DATOS PERSONALES:**
Ambas partes se comprometen a cumplir la Ley 1581 de 2012 y sus decretos reglamentarios. En caso de que la información contenga datos personales:
1. Se aplicarán técnicas de anonimización (k-anonymity, hashing)
2. Solo se procesarán agregados estadísticos
3. Se garantizará el derecho de los titulares (ARCO)
4. Se implementará registro de auditoría completo

**SEXTA - CONFIDENCIALIDAD:**
La información intercambiada tiene carácter **CONFIDENCIAL** y no podrá ser divulgada, publicada ni utilizada para fines diferentes a los establecidos en este convenio, salvo autorización escrita o requerimiento legal.

**SÉPTIMA - SEGURIDAD DE LA INFORMACIÓN:**
EL MINISTERIO implementará:
- Cifrado en tránsito (TLS 1.3) y en reposo (KMS)
- Control de acceso basado en roles (IAM + MFA)
- Auditoría completa de accesos (retención 7 años)
- Backups cifrados con eliminación segura

**OCTAVA - PROPIEDAD INTELECTUAL:**
La información suministrada por LA DISTRIBUIDORA permanece bajo su propiedad. Los modelos, análisis y productos derivados desarrollados por EL MINISTERIO son propiedad del Estado colombiano.

**NOVENA - VIGENCIA:**
El presente convenio tendrá una vigencia de **DOS (2) AÑOS** contados a partir de la fecha de suscripción, prorrogables automáticamente por períodos iguales salvo manifestación en contrario con 60 días de antelación.

**DÉCIMA - TERMINACIÓN:**
El convenio podrá terminarse anticipadamente por:
1. Mutuo acuerdo de las partes
2. Incumplimiento grave de obligaciones (previo requerimiento 30 días)
3. Modificación del marco legal que haga improcedente el intercambio

**DÉCIMA PRIMERA - RESOLUCIÓN DE CONTROVERSIAS:**
Cualquier controversia se resolverá de manera amigable. De no ser posible, se someterá a la jurisdicción administrativa colombiana.

**DÉCIMA SEGUNDA - CLÁUSULA PENAL:**
En caso de divulgación no autorizada o uso indebido de la información, la parte infractora pagará una suma equivalente a **CIEN (100) SMLMV** sin perjuicio de las acciones legales correspondientes.

---

**Firma en señal de aceptación:**

**POR EL MINISTERIO:**  
_______________________________  
[Nombre]  
[Cargo]  
C.C. [Número]

**POR LA DISTRIBUIDORA:**  
_______________________________  
[Nombre]  
[Cargo]  
C.C. [Número]

**Fecha:** _____________________

---

### ANEXO 1 - ESPECIFICACIÓN TÉCNICA DE INFORMACIÓN

| Información | Periodicidad | Formato | Nivel de agregación |
|-------------|--------------|---------|---------------------|
| Pérdidas técnicas y comerciales | Mensual | CSV/Parquet | Por OR |
| Consumo por estrato | Mensual | CSV/Parquet | Municipal (NO individual) |
| Índices calidad (DES/FES) | Mensual | CSV/Parquet | Por OR |
| Infraestructura de red | Anual | CSV/GIS | Agregado |
| Usuarios por estrato | Mensual | CSV | Agregado (NO nominales) |

**Método de transferencia:** SFTP seguro o API REST con autenticación OAuth2

---

<a name="3-nda"></a>
## 3. NDA - ACUERDO DE CONFIDENCIALIDAD

### ACUERDO DE CONFIDENCIALIDAD Y NO DIVULGACIÓN  
**Sistema SIEA - Ministerio de Minas y Energía**

**ENTRE:**

**MINISTERIO DE MINAS Y ENERGÍA**, representado por [NOMBRE], en adelante **"EL MINISTERIO"**

**Y**

**[NOMBRE COMPLETO]**, identificado con C.C. [NÚMERO], en calidad de [CARGO/CONTRATISTA], en adelante **"EL FIRMANTE"**

---

### DECLARACIONES

1. EL FIRMANTE tendrá acceso a información confidencial y/o reservada del sistema SIEA en el cumplimiento de sus funciones.
2. Esta información incluye, sin limitarse a:
   - Datos del sector eléctrico (técnicos, operativos, comerciales)
   - Código fuente del sistema SIEA
   - Credenciales de acceso a APIs y servicios externos
   - Configuraciones de seguridad e infraestructura
   - Modelos de machine learning y algoritmos propietarios
   - Información sujeta a convenios con distribuidoras

---

### CLÁUSULAS

**PRIMERA - OBLIGACIÓN DE CONFIDENCIALIDAD:**  
EL FIRMANTE se compromete a:
1. Mantener absoluta confidencialidad sobre toda la información a la que tenga acceso
2. No divulgar, revelar, publicar, compartir o distribuir información confidencial a terceros
3. No utilizar la información para fines diferentes a los laborales autorizados
4. No reproducir, copiar o extraer información fuera de los sistemas autorizados

**SEGUNDA - MEDIDAS DE PROTECCIÓN:**  
EL FIRMANTE implementará:
1. Contraseñas seguras (mínimo 12 caracteres, alfanumérica + símbolos)
2. MFA (autenticación multifactor) obligatoria
3. No compartir credenciales con terceros
4. No acceder desde redes públicas inseguras
5. Reportar inmediatamente cualquier incidente de seguridad
6. Bloquear sesión al ausentarse del puesto de trabajo

**TERCERA - PROHIBICIONES:**  
Queda expresamente prohibido:
1. Capturar pantallas o fotografías de información confidencial
2. Descargar datos a dispositivos personales (USB, laptop personal, teléfono)
3. Enviar información confidencial por correo personal o mensajería no autorizada
4. Discutir información confidencial en lugares públicos o redes sociales
5. Revelar existencia de vulnerabilidades de seguridad sin autorización

**CUARTA - DEVOLUCIÓN/DESTRUCCIÓN:**  
Al finalizar la relación laboral/contractual, EL FIRMANTE deberá:
1. Devolver todos los dispositivos y credenciales asignados
2. Eliminar cualquier copia de información confidencial en dispositivos personales
3. Certificar por escrito la destrucción/devolución de información

**QUINTA - VIGENCIA:**  
Esta obligación de confidencialidad permanece vigente:
- Durante la relación laboral/contractual
- **CINCO (5) AÑOS** después de finalizada la relación
- **INDEFINIDAMENTE** para información clasificada como secreto industrial

**SEXTA - CONSECUENCIAS DE INCUMPLIMIENTO:**  
El incumplimiento de este acuerdo puede resultar en:
1. Terminación inmediata del contrato/relación laboral
2. Acciones legales civiles y penales
3. Indemnización por daños y perjuicios
4. Reporte a autoridades competentes (SIC, Fiscalía)

**SÉPTIMA - LEY APLICABLE:**  
Este acuerdo se rige por las leyes colombianas, incluyendo:
- Ley 1581 de 2012 (Protección de Datos)
- Ley 1273 de 2009 (Delitos informáticos)
- Código Penal (violación de secreto profesional)

---

**ACEPTACIÓN:**

Yo, [NOMBRE COMPLETO], identificado con C.C. [NÚMERO], declaro que:
- He leído y comprendido este acuerdo en su totalidad
- Acepto todas las obligaciones y restricciones establecidas
- Me comprometo a cumplir estrictamente con lo pactado
- Entiendo las consecuencias del incumplimiento

_______________________________  
Firma del Firmante

_______________________________  
Nombre completo

C.C. _________________________  
Fecha: _______________________

---

**POR EL MINISTERIO:**

_______________________________  
[Nombre]  
[Cargo]  
Fecha: _______________________

---

<a name="4-politica-retencion"></a>
## 4. POLÍTICA DE RETENCIÓN Y ELIMINACIÓN DE DATOS

### POLÍTICA DE RETENCIÓN Y ELIMINACIÓN DE INFORMACIÓN  
**Sistema SIEA - Ministerio de Minas y Energía**

**Versión:** 1.0  
**Fecha de aprobación:** [FECHA]  
**Responsable:** [Oficial de Protección de Datos]

---

### 1. OBJETIVO

Establecer los períodos de retención y procedimientos de eliminación segura de información procesada por el sistema SIEA, en cumplimiento de:
- Ley 1581 de 2012 (Protección de Datos Personales)
- Ley 594 de 2000 (Archivo General de la Nación)
- Acuerdo AGN 004 de 2019 (Tablas de Retención Documental)

---

### 2. ALCANCE

Aplica a toda la información procesada, almacenada o transmitida por SIEA:
- Datos operacionales del sector eléctrico
- Logs de auditoría y seguridad
- Modelos de machine learning
- Backups y copias de seguridad
- Datos personales anonimizados/agregados

---

### 3. CLASIFICACIÓN Y RETENCIÓN

| Categoría | Descripción | Retención | Base legal |
|-----------|-------------|-----------|------------|
| **Datos operacionales** | Demanda, generación, precios, pérdidas | 7 años | Acuerdo AGN 004/2019 |
| **Logs de auditoría** | Accesos, consultas, modificaciones | 7 años | Ley 1581/2012 Art. 17 |
| **Datos personales agregados** | Consumo por estrato/municipio | 3 años | Principio minimización |
| **Modelos ML productivos** | Modelos en producción versionados | Indefinido | Continuidad operativa |
| **Experimentos ML** | Modelos en desarrollo/pruebas | 1 año | Gestión documental |
| **Backups diarios** | Copias de seguridad incrementales | 3 meses | Recuperación ante desastres |
| **Backups mensuales** | Copias de seguridad completas | 1 año | Recuperación ante desastres |
| **Código fuente** | Repositorio Git | Indefinido | Propiedad intelectual Estado |
| **Documentación técnica** | Manuales, diagramas, especificaciones | 10 años | Archivo gestión |
| **Contratos y convenios** | Convenios con distribuidoras, NDAs | 10 años | Acuerdo AGN 004/2019 |

---

### 4. PROCEDIMIENTO DE ELIMINACIÓN

#### 4.1 Eliminación Automática
- Sistema automatizado revisa semanalmente datos que exceden retención
- Notificación al responsable 15 días antes de eliminación
- Eliminación automática si no hay objeción

#### 4.2 Métodos de Eliminación Segura

**Para datos digitales:**
1. **Sobrescritura múltiple** (NIST SP 800-88):
   - 3 pasadas con patrones aleatorios
   - Verificación de eliminación exitosa
   - Certificado de destrucción generado automáticamente

2. **Eliminación de backups:**
   - Eliminación física de medios (degaussing para cintas)
   - Destrucción física de discos obsoletos (trituración)
   - Certificado de destrucción por proveedor autorizado

**Para documentos físicos:**
1. Trituración cruzada (partículas < 4mm²)
2. Certificado de destrucción
3. Registro en acta de eliminación

#### 4.3 Registro de Eliminación

Cada eliminación queda registrada en:
- **Tabla audit_deletion**:
  - Tipo de información eliminada
  - Cantidad de registros
  - Fecha y hora
  - Usuario responsable
  - Método de eliminación
  - Hash del certificado de destrucción

---

### 5. EXCEPCIONES A LA ELIMINACIÓN

**No se eliminarán datos si:**
1. Existe proceso judicial en curso que los requiera
2. Investigación disciplinaria o administrativa en trámite
3. Auditoría externa pendiente
4. Requerimiento de autoridad competente (SIC, Fiscalía, Contraloría)

**Procedimiento:**
1. Responsable solicita congelamiento de eliminación
2. Justificación por escrito
3. Aprobación del Oficial de Protección de Datos
4. Registro en log de excepciones
5. Revisión trimestral de excepciones vigentes

---

### 6. DERECHOS DE LOS TITULARES

Los titulares de datos personales pueden ejercer:

**Derecho de Supresión:**
1. Solicitud por escrito a datospersonales@minenergia.gov.co
2. Identificación del titular y datos a suprimir
3. Evaluación de procedencia (máximo 15 días hábiles)
4. Si procede: eliminación inmediata + confirmación
5. Si no procede: justificación legal

**Limitaciones:**
- No procede si existe obligación legal de retención
- No procede para datos agregados/anonimizados (no son "personales")

---

### 7. BACKUPS Y RECUPERACIÓN

**Política de backups:**
- **Diarios:** Retención 3 meses (90 días)
- **Semanales:** Retención 6 meses
- **Mensuales:** Retención 1 año
- **Anuales:** Retención 3 años

**Eliminación de backups:**
- Backups antiguos se eliminan automáticamente al exceder retención
- Método: Sobrescritura NIST SP 800-88
- Certificado de destrucción generado y almacenado 7 años

**Recuperación:**
- Datos eliminados de producción NO se restauran desde backups (salvo error técnico demostrado)
- Validación de fechas antes de restauración

---

### 8. AUDITORÍA Y CUMPLIMIENTO

**Auditoría semestral:**
- Revisión de cumplimiento de períodos de retención
- Verificación de eliminaciones ejecutadas
- Revisión de excepciones vigentes
- Informe al Oficial de Protección de Datos

**Sanciones por incumplimiento:**
- Disciplinarias (para funcionarios públicos)
- Contractuales (para contratistas)
- Legales (Ley 1581/2012: multas hasta 2.000 SMLMV)

---

### 9. ACTUALIZACIÓN DE LA POLÍTICA

Esta política se revisará:
- Anualmente (revisión programada)
- Cuando cambie legislación aplicable
- Cuando cambie arquitectura técnica de SIEA
- A solicitud del Oficial de Protección de Datos

**Versiones:**
| Versión | Fecha | Cambios | Aprobador |
|---------|-------|---------|-----------|
| 1.0 | [FECHA] | Versión inicial | [Nombre] |

---

### 10. APROBACIONES

**Elaborado por:**  
[Nombre] - [Cargo]  
Fecha: _______________

**Revisado por:**  
[Nombre Oficial de Protección de Datos]  
Fecha: _______________

**Aprobado por:**  
[Nombre Secretario General]  
Fecha: _______________

---

<a name="5-consentimiento-informado"></a>
## 5. CONSENTIMIENTO INFORMADO (SI APLICA)

### AVISO DE PRIVACIDAD Y CONSENTIMIENTO INFORMADO  
**Sistema SIEA - Ministerio de Minas y Energía**

**NOTA:** Este documento solo aplica si SIEA procesa datos personales directamente recolectados de ciudadanos (ej: formularios, chat directo con ciudadanos). Si solo se procesan datos agregados de SUI/XM, este consentimiento NO es necesario.

---

#### ¿Quién es el responsable del tratamiento?
**MINISTERIO DE MINAS Y ENERGÍA**  
NIT: 899.999.007-6  
Dirección: Calle 43 #57-31, Bogotá, Colombia  
Correo: datospersonales@minenergia.gov.co  
Teléfono: (601) 220 0300

#### ¿Qué datos recolectamos?
- Nombre y apellidos
- Correo electrónico
- Teléfono (opcional)
- Pregunta o consulta realizada al asistente

#### ¿Para qué usamos sus datos?
- Responder su consulta sobre el sector energético
- Mejorar el sistema SIEA (análisis estadístico de consultas frecuentes)
- Cumplir obligaciones legales del Ministerio

#### ¿Con quién compartimos sus datos?
- NO compartimos sus datos con terceros comerciales
- Podemos compartir datos anonimizados para fines estadísticos o de investigación

#### ¿Cuánto tiempo conservamos sus datos?
- Consultas realizadas: 1 año
- Logs de auditoría: 7 años (solo registro de interacción, no contenido completo)

#### Sus derechos (ARCO):
- **Acceder** a sus datos
- **Rectificar** datos inexactos
- **Suprimir** sus datos (cuando sea legal)
- **Oponerse** al tratamiento

Para ejercer sus derechos: datospersonales@minenergia.gov.co

#### ¿Es obligatorio proporcionar los datos?
NO. Pero sin ellos no podremos responder su consulta.

---

**CONSENTIMIENTO:**

☐ Autorizo al Ministerio de Minas y Energía a tratar mis datos personales según lo descrito.

Nombre: ______________________________  
Firma: _______________________________  
Fecha: _______________________________

---

## 📞 CONTACTO PARA ASUNTOS LEGALES

**Oficial de Protección de Datos:**  
[Nombre]  
[Cargo]  
Correo: datospersonales@minenergia.gov.co  
Teléfono: [TELÉFONO]

**Área Jurídica:**  
[Nombre]  
[Cargo]  
Correo: juridica@minenergia.gov.co

---

**FIN DEL DOCUMENTO**

*Este documento es de uso interno del Ministerio de Minas y Energía. Requiere aprobación del Área Jurídica antes de su implementación.*
