/**
 * EnergIA — Pantalla principal (Phase 2: wake word integrado)
 *
 * Flujos de activación:
 *  1. Push FCM (8:05 AM) → reproduce automáticamente
 *  2. Wake word "EnergIA" (o "Porcupine" en dev) → reproduce al instante
 *  3. Toque manual en botón "Escuchar informe de hoy"
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  StatusBar,
  Alert,
  Animated,
  Easing,
} from 'react-native';
import messaging from '@react-native-firebase/messaging';
import { playAudioFromUrl, stopAudio } from '../services/audioService';
import { registerForPushNotifications, InformePushData } from '../services/pushService';
import { useWakeWord } from '../hooks/useWakeWord';
import { API_V1_URL, API_KEY } from '../config';

type Estado = 'idle' | 'cargando' | 'reproduciendo' | 'error';

export default function HomeScreen() {
  const [estado, setEstado] = useState<Estado>('idle');
  const [fecha, setFecha] = useState<string>('');
  const [textoPreview, setTextoPreview] = useState<string>('');

  // Datos del último push recibido (para evitar re-fetches innecesarios)
  const latestPushData = useRef<InformePushData | null>(null);

  // Animación del ícono de micrófono cuando está escuchando
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // ── Wake word ─────────────────────────────────────────────────────────
  const { listening: wakeListening, permissionDenied, toggleListener } = useWakeWord({
    onDetected: () => {
      console.log('[HomeScreen] Wake word detectado → reproduciendo informe');
      reproducirInforme();
    },
    enabled: true,
  });

  // Animación pulsante del punto verde cuando el micrófono está activo
  useEffect(() => {
    if (wakeListening) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.4,
            duration: 800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 800,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ])
      ).start();
    } else {
      pulseAnim.stopAnimation();
      pulseAnim.setValue(1);
    }
  }, [wakeListening, pulseAnim]);

  // ── Registro FCM al montar ──────────────────────────────
  useEffect(() => {
    registerForPushNotifications().catch(console.error);
  }, []);

  // ── Listener: push EN PRIMER PLANO → reproducir automáticamente ──
  useEffect(() => {
    const unsubFg = messaging().onMessage(async (remoteMessage) => {
      const data = remoteMessage.data as unknown as InformePushData;
      if (data?.type === 'informe_diario') {
        latestPushData.current = data;
        setFecha(data.fecha ?? '');
        setTextoPreview(data.texto_narrado ?? '');
        await reproducirInforme(data.audio_url);
      }
    });

    return unsubFg;
  }, []);

  // ── Listener: usuario tocó notification (app en bg/cerrada) ──
  useEffect(() => {
    // Notificación que abrió la app (background)
    messaging()
      .getInitialNotification()
      .then((remoteMessage) => {
        if (!remoteMessage) return;
        const data = remoteMessage.data as unknown as InformePushData;
        if (data?.type === 'informe_diario') {
          latestPushData.current = data;
          setFecha(data.fecha ?? '');
          setTextoPreview(data.texto_narrado ?? '');
          reproducirInforme(data.audio_url);
        }
      });

    // Notificación desde background → foreground
    const unsubBg = messaging().onNotificationOpenedApp((remoteMessage) => {
      const data = remoteMessage.data as unknown as InformePushData;
      if (data?.type === 'informe_diario') {
        latestPushData.current = data;
        setFecha(data.fecha ?? '');
        setTextoPreview(data.texto_narrado ?? '');
        reproducirInforme(data.audio_url);
      }
    });

    return unsubBg;
  }, []);

  // ── Reproducción ────────────────────────────────────────
  const reproducirInforme = async (audioUrl?: string) => {
    if (estado === 'cargando' || estado === 'reproduciendo') return;
    const url = audioUrl ?? `${API_V1_URL}/energia-app/audio/informe-diario`;
    setEstado('cargando');
    try {
      await playAudioFromUrl(url, API_KEY, {
        onStart: () => setEstado('reproduciendo'),
        onEnd: () => setEstado('idle'),
        onError: (err) => {
          setEstado('error');
          Alert.alert('Error de audio', err);
        },
      });
    } catch {
      setEstado('error');
    }
  };

  const detener = () => {
    stopAudio();
    setEstado('idle');
  };

  // ── UI ──────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0D1B2A" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>⚡ EnergIA</Text>
        <Text style={styles.headerSub}>Portal Energético · Ministerio de Minas</Text>
      </View>

      {/* Card informe */}
      <View style={styles.card}>
        <Text style={styles.cardLabel}>
          {fecha ? `Informe — ${fecha}` : 'Informe Energético Diario'}
        </Text>
        {textoPreview ? (
          <Text style={styles.cardPreview} numberOfLines={5}>
            {textoPreview}
          </Text>
        ) : (
          <Text style={styles.cardHint}>
            Di <Text style={styles.wakeWord}>&quot;EnergIA&quot;</Text> para escuchar el
            resumen, o espera la notificación de las 8:05 a.m.
          </Text>
        )}
      </View>

      {/* Wake word indicator */}
      <View style={styles.wakeRow}>
        <Animated.View
          style={[
            styles.micDot,
            wakeListening ? styles.micDotActive : styles.micDotIdle,
            { transform: [{ scale: pulseAnim }] },
          ]}
        />
        <Text style={styles.wakeStatus}>
          {permissionDenied
            ? '🎙 Permiso de micrófono denegado'
            : wakeListening
            ? '🎙 Escuchando "EnergIA"…'
            : '🎙 Micrófono pausado'}
        </Text>
        <TouchableOpacity onPress={toggleListener} style={styles.toggleBtn}>
          <Text style={styles.toggleBtnText}>{wakeListening ? 'Pausar' : 'Activar'}</Text>
        </TouchableOpacity>
      </View>

      {/* Botón principal */}
      <View style={styles.controls}>
        {estado === 'cargando' ? (
          <ActivityIndicator size="large" color="#F5A623" />
        ) : estado === 'reproduciendo' ? (
          <TouchableOpacity style={[styles.btn, styles.btnStop]} onPress={detener}>
            <Text style={styles.btnText}>⏹  Detener</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            style={[styles.btn, styles.btnPlay]}
            onPress={() => reproducirInforme()}
          >
            <Text style={styles.btnText}>▶  Escuchar informe de hoy</Text>
          </TouchableOpacity>
        )}
        {estado === 'error' && (
          <Text style={styles.errorText}>
            No se pudo reproducir el audio. Verifica tu conexión.
          </Text>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0D1B2A' },
  header: {
    paddingVertical: 24,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#1B3D6E',
  },
  headerTitle: { fontSize: 26, fontWeight: '800', color: '#F5A623' },
  headerSub: { fontSize: 13, color: '#8EA8C3', marginTop: 2 },
  card: {
    margin: 20,
    padding: 20,
    backgroundColor: '#1B3D6E',
    borderRadius: 16,
    elevation: 4,
  },
  cardLabel: { fontSize: 14, color: '#8EA8C3', marginBottom: 10, fontWeight: '600' },
  cardPreview: { fontSize: 15, color: '#E8F0FE', lineHeight: 22 },
  cardHint: { fontSize: 14, color: '#5A7FA0', fontStyle: 'italic', lineHeight: 20 },
  wakeWord: { color: '#F5A623', fontWeight: '700', fontStyle: 'normal' },

  // ── Wake word indicator row ──────────────────────────────────────
  wakeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 20,
    marginBottom: 8,
    gap: 10,
  },
  micDot: { width: 12, height: 12, borderRadius: 6 },
  micDotActive: { backgroundColor: '#27AE60' },
  micDotIdle: { backgroundColor: '#3D5166' },
  wakeStatus: { flex: 1, fontSize: 13, color: '#8EA8C3' },
  toggleBtn: {
    paddingHorizontal: 14,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#F5A623',
  },
  toggleBtnText: { color: '#F5A623', fontSize: 12, fontWeight: '600' },

  controls: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 30 },
  btn: {
    width: '100%',
    paddingVertical: 18,
    borderRadius: 50,
    alignItems: 'center',
    elevation: 6,
  },
  btnPlay: { backgroundColor: '#F5A623' },
  btnStop: { backgroundColor: '#C0392B' },
  btnText: { fontSize: 17, fontWeight: '700', color: '#0D1B2A' },
  errorText: { marginTop: 16, color: '#E74C3C', fontSize: 13, textAlign: 'center' },
});
