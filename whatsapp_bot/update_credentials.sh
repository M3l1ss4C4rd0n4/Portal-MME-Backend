#!/bin/bash

echo "🔑 Actualizando credenciales de Twilio..."
echo ""
echo "Ve a: https://console.twilio.com"
echo "Y copia tus credenciales REALES:"
echo ""
read -p "TWILIO_ACCOUNT_SID (AC...): " ACCOUNT_SID
read -p "TWILIO_AUTH_TOKEN: " AUTH_TOKEN
echo ""

# Actualizar .env
cd /home/admonctrlxm/server/whatsapp_bot

sed -i "s/^TWILIO_ACCOUNT_SID=.*/TWILIO_ACCOUNT_SID=$ACCOUNT_SID/" .env
sed -i "s/^TWILIO_AUTH_TOKEN=.*/TWILIO_AUTH_TOKEN=$AUTH_TOKEN/" .env

echo "✅ Credenciales actualizadas en .env"
echo ""
echo "Reiniciando bot..."

# Reiniciar bot
pkill -f "uvicorn app.main:app"
sleep 2

cd /home/admonctrlxm/server/whatsapp_bot
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &

echo ""
echo "✅ Bot reiniciado!"
echo ""
echo "Ahora envía 'hola' desde WhatsApp al número de Twilio"
