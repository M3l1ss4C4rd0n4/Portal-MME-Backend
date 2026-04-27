/**
 * EnergIA — App root
 *
 * Punto de entrada React. Verifica si hay un audio pendiente
 * (guardado cuando llegó el push con la app cerrada) y lo pasa
 * a HomeScreen para reproducción automática.
 */
import React, { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import HomeScreen from './src/screens/HomeScreen';

export default function App() {
  // Limpiar token pendiente en AsyncStorage al montar
  // (HomeScreen se encarga de reproducir si hay algo pendiente)
  useEffect(() => {
    AsyncStorage.getItem('@energia_pending_audio').then((raw) => {
      if (raw) AsyncStorage.removeItem('@energia_pending_audio');
    });
  }, []);

  return <HomeScreen />;
}
