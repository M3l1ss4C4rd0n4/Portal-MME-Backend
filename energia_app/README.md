# EnergIA App — Setup Guide

## Requisitos previos

```bash
node >= 18
npm >= 10
Java JDK 17  (para builds Android)
Android Studio + SDK 34
```

## 1. Instalar dependencias

```bash
cd energia_app
npm install
```

## 2. Firebase — Crear proyecto

1. Ir a [Firebase Console](https://console.firebase.google.com/) → "Nuevo proyecto" → **EnergIA**
2. Agregar app Android:
   - Package name: `co.gov.minminas.energia`
   - Descargar `google-services.json` → copiarlo a `android/app/google-services.json`
3. Ir a **Configuración del proyecto → Cuentas de servicio → Generar nueva clave privada**
   - Guardar el JSON resultante en el servidor: `/home/admonctrlxm/server/credentials/firebase-energia.json`
4. Agregar a `server/.env`:
   ```
   FIREBASE_CREDENTIALS_PATH=/home/admonctrlxm/server/credentials/firebase-energia.json
   API_BASE_URL=https://TU_DOMINIO_PUBLICO
   ```

## 3. Configurar URL de la API

Editar `src/config.ts`:
```ts
export const API_BASE_URL = 'https://TU_DOMINIO_PUBLICO';
```

O pasar via variable de entorno en el CI/CD:
```bash
ENERGIA_API_URL=https://... npx react-native run-android
```

## 4. Ejecutar en emulador

```bash
npm start           # Metro bundler
npm run android     # Instala en emulador/dispositivo
```

## 5. Generar APK de release

```bash
cd android
./gradlew assembleRelease
# APK: android/app/build/outputs/apk/release/app-release.apk
```

## 6. Probar push notification manualmente

```bash
# Registrar un token de prueba vía API
curl -X POST https://TU_DOMINIO/v1/energia-app/push/registrar \
  -H "X-API-Key: TU_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"fcm_token":"TOKEN_DEL_EMULADOR","usuario_id":"dev-test","dispositivo":"Emulador"}'

# Lanzar la tarea Celery manualmente (sin esperar las 8am)
cd /home/admonctrlxm/server && source venv/bin/activate
python -c "from tasks.push_tasks import enviar_informe_diario_push; enviar_informe_diario_push.delay()"
```

## Arquitectura del flujo

```
8:05 AM  →  Celery Beat (servidor)
              │
              ├─ Orquestador → informe_ejecutivo
              ├─ Groq LLM → narración oral
              └─ FCM multicast → todos los tokens activos
                                      │
                            [Dispositivo Android]
                              │
                              ├─ App en 1er plano → reproduce MP3 automáticamente
                              ├─ App en bg → muestra notificación, al tap → reproduce
                              └─ App cerrada → al abrir → reproduce desde URL guardada
```
