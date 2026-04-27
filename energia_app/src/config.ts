/**
 * EnergIA — Configuración de la app
 *
 * En producción, reemplazar los valores con las URLs y keys reales.
 * IMPORTANTE: No subir API_KEY a repositorios públicos.
 * Para builds de release, inyectar via variables de entorno en el CI/CD.
 */
export const API_BASE_URL: string =
  process.env.ENERGIA_API_URL ?? 'https://portalenergetico.minenergia.gov.co';

/** URL base de la API versionada (incluye el prefijo /api que espera nginx). */
export const API_V1_URL: string = `${API_BASE_URL}/api/v1`;

export const API_KEY: string =
  process.env.ENERGIA_API_KEY ?? '8CE0f5epgdDol60O6zqD3owlo5zTzb6q0HJ1vhL_epo';

/**
 * Idioma para el reconocimiento de voz (STT nativo Android).
 * Valores válidos: 'es-CO', 'es-ES', 'es-MX'
 */
export const VOICE_LOCALE: string = 'es-CO';

