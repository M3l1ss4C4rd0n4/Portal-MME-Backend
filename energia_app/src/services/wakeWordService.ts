/**
 * EnergIA — Servicio de Wake Word (STT nativo via @react-native-voice/voice)
 *
 * Estrategia: escucha continua con reinicio automático.
 * Cuando el texto reconocido contiene la palabra trigger ("energía"),
 * invoca el callback registrado.
 *
 * Compatible con RN 0.76+ (bridge legacy activado por defecto).
 */
import Voice, { SpeechResultsEvent, SpeechErrorEvent } from '@react-native-voice/voice';
import { VOICE_LOCALE } from '../config';

// Palabras que activan la acción (insensible a mayúsculas/tildes)
const TRIGGER_WORDS = ['energía', 'energia', 'energy'];

export type WakeWordCallback = () => void;

let _isListening = false;
let _onWakeWord: WakeWordCallback | null = null;
let _onError: ((err: Error) => void) | null = null;
let _destroyed = false;

// ── Handlers internos ────────────────────────────────────────────────

function _normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, ''); // quita tildes
}

function _handleResults(e: SpeechResultsEvent) {
  const values = e.value ?? [];
  const matched = values.some((v) =>
    TRIGGER_WORDS.some((t) => _normalize(v).includes(_normalize(t)))
  );
  if (matched) {
    console.log('[WAKE-WORD] ¡Detectado "Energía" (STT)!');
    _onWakeWord?.();
    // Pausa breve antes de reiniciar para evitar activación doble
    setTimeout(_restartIfActive, 1200);
  }
}

function _handleError(e: SpeechErrorEvent) {
  const msg = e.error?.message ?? String(e.error);
  // Errores de timeout/sin audio son normales en escucha continua → reiniciar silenciosamente
  const isBenign =
    msg.includes('7') ||        // ERROR_NO_MATCH
    msg.includes('6') ||        // ERROR_SPEECH_TIMEOUT
    msg.includes('timeout') ||
    msg.includes('no match');
  if (!isBenign) {
    console.warn('[WAKE-WORD] Error STT:', msg);
    _onError?.(new Error(msg));
  }
  _restartIfActive();
}

function _handleEnd() {
  _restartIfActive();
}

async function _restartIfActive() {
  if (!_isListening || _destroyed) return;
  // Pequeña pausa para evitar loop tight en caso de error continuo
  await new Promise((r) => setTimeout(r, 400));
  if (!_isListening || _destroyed) return;
  try {
    await Voice.start(VOICE_LOCALE);
  } catch (err) {
    console.warn('[WAKE-WORD] Error reiniciando STT:', err);
  }
}

// ── API pública ───────────────────────────────────────────────────────

export async function startWakeWordListener(
  onWakeWord: WakeWordCallback,
  onError?: (err: Error) => void,
): Promise<void> {
  if (_isListening) return;

  _destroyed = false;
  _onWakeWord = onWakeWord;
  _onError = onError ?? null;

  Voice.onSpeechResults = _handleResults;
  Voice.onSpeechError = _handleError;
  Voice.onSpeechEnd = _handleEnd;

  try {
    await Voice.start(VOICE_LOCALE);
    _isListening = true;
    console.log('[WAKE-WORD] Escuchando con STT nativo (locale:', VOICE_LOCALE, ')…');
  } catch (err) {
    console.error('[WAKE-WORD] Error iniciando STT:', err);
    _onError?.(err instanceof Error ? err : new Error(String(err)));
  }
}

export async function stopWakeWordListener(): Promise<void> {
  if (!_isListening) return;

  _destroyed = true;
  _isListening = false;
  _onWakeWord = null;
  _onError = null;

  Voice.onSpeechResults = undefined;
  Voice.onSpeechError = undefined;
  Voice.onSpeechEnd = undefined;

  try {
    await Voice.stop();
    await Voice.destroy();
  } catch (err) {
    console.warn('[WAKE-WORD] Error al detener STT:', err);
  }

  console.log('[WAKE-WORD] STT detenido');
}

export function isWakeWordListening(): boolean {
  return _isListening;
}


