/**
 * EnergIA — Servicio de push notifications (FCM)
 * Maneja la suscripción FCM y el registro del token en la API del servidor.
 */
import messaging from '@react-native-firebase/messaging';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_V1_URL, API_KEY } from '../config';

const STORAGE_KEY_TOKEN = '@energia_fcm_token';
const STORAGE_KEY_USUARIO = '@energia_usuario_id';

/** Genera un ID de usuario persistente (UUID simple basado en timestamp). */
async function getOrCreateUserId(): Promise<string> {
  let uid = await AsyncStorage.getItem(STORAGE_KEY_USUARIO);
  if (!uid) {
    uid = `app-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    await AsyncStorage.setItem(STORAGE_KEY_USUARIO, uid);
  }
  return uid;
}

/** Solicita permisos FCM (iOS) y registra el token en la API del servidor. */
export async function registerForPushNotifications(): Promise<string | null> {
  // iOS: pedir permiso explícito
  const authStatus = await messaging().requestPermission();
  const enabled =
    authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
    authStatus === messaging.AuthorizationStatus.PROVISIONAL;

  if (!enabled) {
    console.warn('[FCM] Permisos de notificación denegados');
    return null;
  }

  const token = await messaging().getToken();
  if (!token) return null;

  const prevToken = await AsyncStorage.getItem(STORAGE_KEY_TOKEN);
  if (token === prevToken) return token; // sin cambios

  const usuarioId = await getOrCreateUserId();

  try {
    const res = await fetch(`${API_V1_URL}/energia-app/push/registrar`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY,
      },
      body: JSON.stringify({
        fcm_token: token,
        usuario_id: usuarioId,
        dispositivo: 'Android', // TODO: react-native-device-info
      }),
    });
    if (res.ok) {
      await AsyncStorage.setItem(STORAGE_KEY_TOKEN, token);
      console.log('[FCM] Token registrado correctamente');
    }
  } catch (err) {
    console.error('[FCM] Error registrando token:', err);
  }

  return token;
}

/**
 * Tipo del payload de push que envía el servidor.
 */
export interface InformePushData {
  type: 'informe_diario';
  audio_url: string;
  fecha: string;
  texto_narrado?: string;
}
