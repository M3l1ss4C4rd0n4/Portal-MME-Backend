/**
 * EnergIA — Entry point de la app React Native
 *
 * Registra el handler de mensajes FCM en background/terminated
 * (DEBE estar en index.js, fuera de cualquier componente React).
 */
import { AppRegistry } from 'react-native';
import messaging from '@react-native-firebase/messaging';
import App from './App';
import { name as appName } from './package.json';

/**
 * Handler de mensajes FCM cuando la app está en segundo plano o cerrada.
 * Aquí NO podemos reproducir audio directamente (sin UI), pero podemos
 * guardar los datos en AsyncStorage para que HomeScreen los lea al abrirse.
 */
messaging().setBackgroundMessageHandler(async (remoteMessage) => {
  const data = remoteMessage.data;
  if (data?.type === 'informe_diario' && data.audio_url) {
    // Guardar la URL para que HomeScreen la reproduzca al abrir la app
    try {
      const AsyncStorage =
        require('@react-native-async-storage/async-storage').default;
      await AsyncStorage.setItem(
        '@energia_pending_audio',
        JSON.stringify({ audio_url: data.audio_url, fecha: data.fecha })
      );
    } catch (_) {}
  }
});

AppRegistry.registerComponent(appName, () => App);
