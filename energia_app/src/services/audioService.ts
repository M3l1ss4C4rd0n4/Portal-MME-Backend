/**
 * EnergIA — Servicio de audio
 *
 * Flujo:
 *  1. fetch() con X-API-Key header → descarga el MP3 en binario
 *  2. Escribe en archivo temporal (react-native-fs)
 *  3. Sound.play() desde archivo local
 *
 * Soporta GET (informe-diario) y POST (consulta libre).
 */
import Sound from 'react-native-sound';
import RNFS from 'react-native-fs';

Sound.setCategory('Playback');

let _currentSound: Sound | null = null;
let _tempFile: string | null = null;

export interface PlayOptions {
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (err: string) => void;
}

export interface FetchAudioOptions extends PlayOptions {
  method?: 'GET' | 'POST';
  body?: object;        // solo para POST
}

/**
 * Descarga el audio desde la API (GET o POST) usando X-API-Key header
 * y lo reproduce usando Sound desde un archivo temporal.
 */
export async function playAudioFromUrl(
  url: string,
  apiKey: string,
  opts: FetchAudioOptions = {}
): Promise<void> {
  // Limpiar reproducción anterior
  stopAudio();

  const { method = 'GET', body, onStart, onEnd, onError } = opts;

  // ── 1. Descargar MP3 con fetch ────────────────────────────────────
  let response: Response;
  try {
    const fetchOpts: RequestInit = {
      method,
      headers: {
        'X-API-Key': apiKey,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    };
    response = await fetch(url, fetchOpts);
  } catch (err) {
    const msg = `Error de red: ${(err as Error).message}`;
    onError?.(msg);
    throw new Error(msg);
  }

  if (!response.ok) {
    const msg = `Error del servidor: HTTP ${response.status}`;
    onError?.(msg);
    throw new Error(msg);
  }

  // ── 2. Guardar en archivo temporal ────────────────────────────────
  let tempPath: string;
  try {
    const blob = await response.blob();
    const arrayBuf = await (blob as any).arrayBuffer();
    const bytes = Array.from(new Uint8Array(arrayBuf)) as number[];
    const base64 = btoa(String.fromCharCode(...bytes));

    tempPath = `${RNFS.CachesDirectoryPath}/energia_audio_${Date.now()}.mp3`;
    await RNFS.writeFile(tempPath, base64, 'base64');
    _tempFile = tempPath;
  } catch (err) {
    const msg = `Error guardando audio: ${(err as Error).message}`;
    onError?.(msg);
    throw new Error(msg);
  }

  // ── 3. Reproducir desde archivo local ─────────────────────────────
  return new Promise((resolve, reject) => {
    const sound = new Sound(tempPath, '', (error) => {
      if (error) {
        const msg = `Error cargando audio local: ${error.message}`;
        onError?.(msg);
        reject(new Error(msg));
        return;
      }
      _currentSound = sound;
      onStart?.();
      sound.play((success) => {
        sound.release();
        _currentSound = null;
        _cleanTempFile(tempPath);
        if (success) {
          onEnd?.();
          resolve();
        } else {
          const msg = 'Error durante la reproducción';
          onError?.(msg);
          reject(new Error(msg));
        }
      });
    });
  });
}

/** Detiene la reproducción en curso. */
export function stopAudio(): void {
  if (_currentSound) {
    _currentSound.stop();
    _currentSound.release();
    _currentSound = null;
  }
  if (_tempFile) {
    _cleanTempFile(_tempFile);
    _tempFile = null;
  }
}

function _cleanTempFile(path: string) {
  RNFS.unlink(path).catch(() => {/* ignorar si ya fue eliminado */});
}
