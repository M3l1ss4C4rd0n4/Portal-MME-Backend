# Solicitud de información — bases SICOM para los tableros del Viceministerio

> Borrador para enviar al equipo de la Dirección de Hidrocarburos.
> Preparado por el equipo de datos · actualizado 12 de octubre de 2026

---

**Asunto:** Cuenta de servicio para la conexión automática a los cubos SICOM, y dos aclaraciones
sobre los datos

Cordial saludo.

Los tableros de combustibles líquidos del Portal del Viceministerio ya están publicados y, desde
hoy, **se alimentan directamente de los cubos de SICOM**, sin pasar por la exportación manual a
Excel. La conexión usa el mismo mecanismo que describe el instructivo «Consulta de Cubos» del grupo
—usuario y contraseña contra `bi.sicom.gov.co`— solo que ejecutado de forma automática una vez al
día.

Esto resuelve por sí solo las dos situaciones que les habíamos reportado en la versión anterior de
este documento, y que ya **no requieren ninguna acción de su parte**:

| Situación reportada antes | Estado |
|---|---|
| El archivo de Compras EDS llegaba cortado en el límite de filas de Excel | **Resuelta.** La consulta directa no tiene ese límite; la información se descarga completa, separada por año de ciclo. |
| En Compras, el detalle no cuadraba con el total: faltaba el 25,4 % del volumen | **Resuelta, y confirmado que el dato de SICOM estaba bien.** El cubo reporta 347.143 millones y el total que declaraba el propio archivo de Excel era 344.932 millones: prácticamente el mismo. Lo que faltaba se perdía al exportar a mano, no en la fuente. |

Quedan tres puntos en los que sí necesitamos su apoyo.

## 1. Cuenta de servicio para la conexión automática

Hoy la conexión funciona con las credenciales personales de una funcionaria del equipo de datos.
Eso es adecuado para poner el proceso en marcha, pero no para sostenerlo: si esa persona cambia de
funciones o se vence su clave, los tableros del Viceministerio dejan de actualizarse.

**Solicitud:** gestionar ante SICOM una **cuenta de servicio institucional** de solo consulta, a
nombre del Viceministerio de Energía y no de una persona, con acceso a los cubos de Agentes,
Capacidad y Compras. El cambio en nuestro lado es sustituir un valor de configuración; no requiere
modificar el proceso.

## 2. Capacidad operativa: unidad de medida y criterio de registro

Al extraer la información completa encontramos que la capacidad se registra **por ciclo** (año y
mes). Eso explica algo que nos había llamado la atención y que conviene aclarar antes de publicar
cifras agregadas:

- La suma de todos los ciclos desde 2010 da 2,74 billones, pero esa cifra **no es la capacidad
  instalada del país**: es la acumulación de todas las declaraciones hechas a lo largo de 17 años.
- Cuatro ciclos concentran el 94 % de ese total: **2011-09, 2012-05, 2012-06 y 2012-07**, con unos
  645.000 millones cada uno, frente a una mediana de 673 millones en los demás ciclos. Son valores
  atípicos en un factor de mil.
- La columna no indica en qué unidad está expresada (galones, barriles, metros cúbicos).

**Solicitud:** confirmar (a) la unidad de medida, (b) qué representa el valor de cada ciclo —si es
la capacidad vigente en ese mes o un registro incremental—, y (c) si los cuatro ciclos de 2011 y
2012 corresponden a una carga atípica que deba excluirse de los análisis históricos.

## 3. Dos aclaraciones menores

- **Códigos de producto a comercializar.** En la base de Agentes, la columna «Producto a
  comercializar» usa los códigos `N`, `S`, `CLDP` y `CLDP Y GNV`, que no aparecen definidos en la
  documentación recibida. Agradecemos su significado para rotular correctamente el tablero.
- **Agentes sin año de creación.** Un pequeño grupo de agentes no tiene año de creación registrado.
  El tablero lo advierte, pero lo dejamos anotado por si conviene completarlo en la fuente.

## 4. Un punto que quedó resuelto

El Informe de Metodología advertía, en la sección de la base de Compras, que el campo «Tipo agente
comprador» aparecía relacionado dos veces. Al consultar la estructura del cubo quedó aclarado: son
dos campos distintos, «Tipo agente comprador» y «Tipo agente proveedor», acompañados de los
municipios de planta tanto del comprador como del proveedor. No se requiere acción.

---

## Anexo — qué cambia en la práctica para el grupo

El trabajo de consultar los cubos, armar las tablas dinámicas, depurarlas y subirlas a OneDrive deja
de ser necesario para alimentar los tableros del Viceministerio. El proceso automático reproduce esa
misma cadena todos los días y, además, conserva el histórico, deja registro de cada actualización y
concilia las cifras contra el total que declara el propio cubo.

La carpeta de OneDrive se mantiene activa por ahora, para poder comparar ambas rutas durante la
transición. Si el grupo sigue usando esos archivos para sus propios análisis, puede continuar
haciéndolo sin ningún cambio.
