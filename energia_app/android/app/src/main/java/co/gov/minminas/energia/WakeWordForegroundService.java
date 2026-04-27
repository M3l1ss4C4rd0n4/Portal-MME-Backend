package co.gov.minminas.energia;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

/**
 * WakeWordForegroundService
 *
 * Servicio en primer plano para mantener el listener de Porcupine activo
 * cuando la pantalla está apagada o la app está en segundo plano.
 *
 * Se inicia desde React Native a través de un módulo nativo o directamente
 * cuando Porcupine arranca en AppDelegate / MainApplication.
 *
 * Android 14+ requiere foregroundServiceType="microphone" (declarado en
 * AndroidManifest.xml) para acceder al micrófono desde un ForegroundService.
 */
public class WakeWordForegroundService extends Service {

    private static final String CHANNEL_ID   = "wake_word_channel";
    private static final int    NOTIF_ID     = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIF_ID, buildNotification());
        // Porcupine se inicializa desde JS (React Native) — este servicio
        // solo garantiza que el proceso siga vivo.
        return START_STICKY;
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // ── helpers ────────────────────────────────────────────────────────

    private Notification buildNotification() {
        Intent openApp = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
            this, 0, openApp,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("EnergIA escuchando…")
            .setContentText("Di \"EnergIA\" para escuchar el resumen energético")
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pi)
            .setOngoing(true)
            .setSilent(true)
            .build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                CHANNEL_ID,
                "Wake Word EnergIA",
                NotificationManager.IMPORTANCE_LOW
            );
            ch.setDescription("Mantiene el reconocimiento de voz activo en segundo plano");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }
}
