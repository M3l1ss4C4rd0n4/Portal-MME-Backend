/**
 * EnergIA — Hook de wake word
 *
 * Encapsula el ciclo de vida de Porcupine:
 *  - Pide permiso de micrófono al montar
 *  - Inicia el listener automáticamente si tiene permiso
 *  - Para al desmontar (cleanup)
 *  - Expone { listening, permissionDenied, lastDetectedAt }
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { Platform } from 'react-native';
import { check, request, PERMISSIONS, RESULTS } from 'react-native-permissions';
import {
  startWakeWordListener,
  stopWakeWordListener,
} from '../services/wakeWordService';

export interface UseWakeWordOptions {
  /** Callback invocado cada vez que se detecta la palabra clave */
  onDetected: () => void;
  /** Si false, el listener no se inicia aunque haya permiso */
  enabled?: boolean;
}

export interface UseWakeWordState {
  listening: boolean;
  permissionDenied: boolean;
  lastDetectedAt: Date | null;
  toggleListener: () => void;
}

export function useWakeWord({
  onDetected,
  enabled = true,
}: UseWakeWordOptions): UseWakeWordState {
  const [listening, setListening] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [lastDetectedAt, setLastDetectedAt] = useState<Date | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const onDetectedRef = useRef(onDetected);
  onDetectedRef.current = onDetected;

  const handleDetected = useCallback(() => {
    setLastDetectedAt(new Date());
    onDetectedRef.current();
  }, []);

  const requestMicPermission = useCallback(async (): Promise<boolean> => {
    const permission =
      Platform.OS === 'ios'
        ? PERMISSIONS.IOS.MICROPHONE
        : PERMISSIONS.ANDROID.RECORD_AUDIO;

    const current = await check(permission);
    if (current === RESULTS.GRANTED) return true;

    const result = await request(permission);
    return result === RESULTS.GRANTED;
  }, []);

  const startListening = useCallback(async () => {
    const granted = await requestMicPermission();
    if (!granted) {
      setPermissionDenied(true);
      return;
    }
    setPermissionDenied(false);
    await startWakeWordListener(handleDetected, (err) => {
      console.error('[useWakeWord] error:', err);
      setListening(false);
    });
    setListening(true);
  }, [handleDetected, requestMicPermission]);

  const stopListening = useCallback(async () => {
    await stopWakeWordListener();
    setListening(false);
  }, []);

  const toggleListener = useCallback(() => {
    if (listening) {
      stopListening();
    } else {
      startListening();
    }
  }, [listening, startListening, stopListening]);

  // Arrancar automáticamente al montar si enabled=true
  useEffect(() => {
    if (enabled) {
      startListening();
    }
    return () => {
      stopListening();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Solo al montar/desmontar

  return { listening, permissionDenied, lastDetectedAt, toggleListener };
}
