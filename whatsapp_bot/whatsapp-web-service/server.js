const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Cliente WhatsApp
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    }
});

let isReady = false;
let qrCodeData = null;

// Generar QR en consola
client.on('qr', (qr) => {
    console.log('\n📱 ====================================');
    console.log('ESCANEA ESTE CÓDIGO QR CON TU WHATSAPP:');
    console.log('========================================\n');
    qrcode.generate(qr, { small: true });
    console.log('\n========================================');
    console.log('Abre WhatsApp en tu teléfono > Menú > Dispositivos vinculados > Vincular dispositivo');
    console.log('========================================\n');
    qrCodeData = qr;
    isReady = false;
});

// Cliente listo
client.on('ready', () => {
    console.log('✅ WhatsApp Bot conectado y listo');
    console.log('🚀 Servicio escuchando en http://localhost:3000');
    isReady = true;
    qrCodeData = null;
});

// Cliente autenticado
client.on('authenticated', () => {
    console.log('🔐 WhatsApp autenticado correctamente');
});

// Error de autenticación
client.on('auth_failure', (msg) => {
    console.error('❌ Error de autenticación:', msg);
    isReady = false;
});

// Desconexión
client.on('disconnected', (reason) => {
    console.log('⚠️ WhatsApp desconectado:', reason);
    isReady = false;
});

// Recibir mensajes
client.on('message', async (msg) => {
    try {
        const from = msg.from;
        const body = msg.body;
        const hasMedia = msg.hasMedia;
        
        // Extraer número limpio (sin @c.us)
        const phoneNumber = from.replace('@c.us', '');
        
        console.log(`📱 Mensaje de ${phoneNumber}: ${body.substring(0, 50)}...`);
        
        // Enviar a bot Python para procesamiento
        try {
            const response = await axios.post('http://localhost:8001/api/process-message', {
                from_number: phoneNumber,
                body: body,
                has_media: hasMedia,
                provider: 'whatsapp-web'
            }, {
                timeout: 30000
            });
            
            const botResponse = response.data;
            
            // Enviar respuesta
            if (botResponse.body) {
                await msg.reply(botResponse.body);
                console.log(`✅ Respuesta enviada a ${phoneNumber}`);
            }
            
            // Enviar media si existe
            if (botResponse.media_url) {
                // TODO: Implementar envío de media
                console.log(`📎 Media URL: ${botResponse.media_url}`);
            }
            
        } catch (error) {
            console.error('❌ Error procesando con bot Python:', error.message);
            
            // Respuesta básica de fallback
            if (body.toLowerCase() === 'hola') {
                await msg.reply('🔋 *Bienvenido al Bot del Ministerio de Energía*\n\n' +
                    '1️⃣ Precio de Bolsa\n' +
                    '2️⃣ Generación Eléctrica\n' +
                    '3️⃣ Demanda Nacional\n' +
                    '4️⃣ Dashboard Web\n\n' +
                    'Escribe el número de la opción o tu consulta.');
            }
        }
        
    } catch (error) {
        console.error('❌ Error manejando mensaje:', error);
    }
});

// ============ API REST ============

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: isReady ? 'connected' : 'disconnected',
        provider: 'whatsapp-web',
        timestamp: new Date().toISOString(),
        qr_available: qrCodeData !== null
    });
});

// Obtener código QR
app.get('/qr', (req, res) => {
    if (qrCodeData) {
        res.json({
            qr: qrCodeData,
            status: 'waiting_scan',
            message: 'Escanea el código QR con tu WhatsApp'
        });
    } else if (isReady) {
        res.json({
            status: 'connected',
            message: 'WhatsApp ya está conectado'
        });
    } else {
        res.json({
            status: 'initializing',
            message: 'Esperando código QR...'
        });
    }
});

// Enviar mensaje
app.post('/send', async (req, res) => {
    try {
        if (!isReady) {
            return res.status(503).json({
                error: 'WhatsApp no está conectado',
                message: 'Escanea el código QR primero'
            });
        }
        
        const { to, message, media_url } = req.body;
        
        if (!to || !message) {
            return res.status(400).json({
                error: 'Faltan parámetros',
                required: ['to', 'message']
            });
        }
        
        // Formatear número: remover + y agregar @c.us
        let chatId = to.replace('+', '').replace(/\s/g, '');
        if (!chatId.endsWith('@c.us')) {
            chatId = chatId + '@c.us';
        }
        
        // Verificar que el número existe
        const numberExists = await client.isRegisteredUser(chatId);
        if (!numberExists) {
            return res.status(400).json({
                error: 'Número no registrado en WhatsApp',
                number: to
            });
        }
        
        // Enviar mensaje
        const sent = await client.sendMessage(chatId, message);
        
        console.log(`✅ Mensaje enviado a ${to} - ID: ${sent.id.id}`);
        
        res.json({
            success: true,
            message_id: sent.id.id,
            timestamp: sent.timestamp,
            to: to,
            provider: 'whatsapp-web'
        });
        
    } catch (error) {
        console.error('❌ Error enviando mensaje:', error);
        res.status(500).json({
            error: error.message,
            details: error.toString()
        });
    }
});

// Estado del cliente
app.get('/status', async (req, res) => {
    try {
        if (!isReady) {
            return res.json({
                status: 'disconnected',
                ready: false,
                message: 'WhatsApp no conectado'
            });
        }
        
        const state = await client.getState();
        const info = client.info;
        
        res.json({
            status: 'connected',
            ready: isReady,
            state: state,
            phone: info ? info.wid.user : null,
            platform: info ? info.platform : null,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        res.status(500).json({
            error: error.message
        });
    }
});

// Webhook para Twilio (compatibilidad)
app.post('/webhook/whatsapp', async (req, res) => {
    try {
        // Parsear datos de Twilio format
        const from = req.body.From ? req.body.From.replace('whatsapp:', '').trim() : null;
        const body = req.body.Body || '';
        
        if (!from || !body) {
            return res.status(400).json({ error: 'Missing From or Body' });
        }
        
        // Enviar directamente (simular que ya fue procesado por el bot)
        const chatId = from.replace('+', '') + '@c.us';
        
        // El evento 'message' del cliente manejará el procesamiento
        // Aquí solo confirmamos que recibimos el webhook
        
        res.json({
            status: 'received',
            message: 'Webhook procesado por whatsapp-web'
        });
        
    } catch (error) {
        console.error('❌ Error en webhook:', error);
        res.status(500).json({ error: error.message });
    }
});

// ============ INICIAR SERVICIO ============

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
    console.log(`\n🚀 WhatsApp Web Service iniciado en puerto ${PORT}`);
    console.log(`📍 Health: http://localhost:${PORT}/health`);
    console.log(`📍 Status: http://localhost:${PORT}/status`);
    console.log(`📍 QR Code: http://localhost:${PORT}/qr`);
    console.log(`📍 Send: POST http://localhost:${PORT}/send`);
    console.log('\n⏳ Inicializando WhatsApp...\n');
});

// Inicializar cliente WhatsApp
client.initialize();

// Manejo de señales
process.on('SIGINT', async () => {
    console.log('\n⏹️  Deteniendo servicio...');
    await client.destroy();
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\n⏹️  Deteniendo servicio...');
    await client.destroy();
    process.exit(0);
});
