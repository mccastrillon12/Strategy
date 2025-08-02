from telethon.sync import TelegramClient
import MetaTrader5 as mt5
import re
from datetime import datetime, timezone
from pytz import timezone as pytz_timezone
import time

# === CONFIGURACIÓN ===
api_id = 29633269
api_hash = '5c2a5c15e5e7b142d04768b6ae03e974'
group_username = 'GoldTraderMe'
risk_percent = 1  # Riesgo por operación (%)

# === CONEXIÓN A TELEGRAM ===
client = TelegramClient('session_name', api_id, api_hash)

with client:
    signal = None
    for message in client.iter_messages(group_username, limit=100):
        texto = message.message
        if texto is None:
            continue

        indice = re.search(r'([A-Z0-9]+)\s+(BUY|SELL)', texto, re.IGNORECASE)
        entry = re.search(r'ENTRY\s+(\d+)', texto)
        sl = re.search(r'SL\s+(\d+)', texto)
        tps = re.findall(r'TP\s+(\d+)', texto)

        if indice and entry and sl and len(tps) >= 3:
            signal = {
                'symbol': indice.group(1).upper(),
                'tipo': indice.group(2).upper(),
                'entry': float(entry.group(1)),
                'sl': float(sl.group(1)),
                'tp': float(tps[2]),  # Usar TP3
                'date': message.date
            }
            break  # Tomar solo la última válida

if signal is None:
    print("❌ No se encontró una señal válida.")
    exit()

# === CONEXIÓN A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

# === OBTENER BALANCE ACTUAL ===
info = mt5.account_info()
if info is None:
    raise RuntimeError("❌ No se pudo obtener información de la cuenta.")

balance = info.balance
print(f"\n💼 Cuenta: {info.login}")
print(f"💰 Balance actual: ${balance:.2f}")

# === VERIFICAR SI LA SEÑAL ES RECIENTE ===
ahora = datetime.now(timezone.utc)
tiempo_transcurrido = ahora - signal['date']
minutos_pasados = tiempo_transcurrido.total_seconds() / 60

# Convertir hora de la señal a Colombia
colombia_tz = pytz_timezone('America/Bogota')
hora_colombia = signal['date'].astimezone(colombia_tz)

if minutos_pasados > 5:
    print("\n⚠️ La señal tiene más de 5 minutos. No se ejecutará.")
    print(f"🕒 Hora de la señal (Col): {hora_colombia.strftime('%H:%M:%S')}")
    print(f"📌 Índice: {signal['symbol']}")
    print(f"🎯 SL: {signal['sl']}  TP: {signal['tp']}")
    mt5.shutdown()
    exit()

# === CONFIGURAR SÍMBOLO ===
symbol = signal['symbol']
if not mt5.symbol_select(symbol, True):
    raise RuntimeError(f"❌ No se pudo seleccionar el símbolo {symbol}")

# === CÁLCULO DEL LOTAJE POR RIESGO ===
tick = mt5.symbol_info_tick(symbol)
price = tick.ask if signal['tipo'] == 'BUY' else tick.bid
sl_distance = abs(price - signal['sl'])

if sl_distance == 0:
    raise ValueError("❌ SL y precio actual son iguales. No se puede calcular el lote.")

risk_dollars = balance * (risk_percent / 100)
lot_size = risk_dollars / sl_distance
lot_size = round(max(lot_size, 0.01), 2)  # mínimo 0.01 lote

# === CONFIGURAR ORDEN ===
order_type = mt5.ORDER_TYPE_BUY if signal['tipo'] == 'BUY' else mt5.ORDER_TYPE_SELL
sl = signal['sl']
tp = signal['tp']

request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": symbol,
    "volume": lot_size,
    "type": order_type,
    "price": tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid,
    "sl": sl,
    "tp": tp,
    "deviation": 10,
    "magic": 1001,
    "comment": "AutoSignalTelegram",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

# === EJECUTAR ORDEN ===
result = mt5.order_send(request)

if result.retcode == mt5.TRADE_RETCODE_DONE:
    print(f"\n✅ Orden ejecutada correctamente:")
    print(f"📌 Símbolo: {symbol}")
    print(f"📈 Tipo: {signal['tipo']}")
    print(f"🎯 Entrada: {request['price']}  SL: {sl}  TP: {tp}")
    print(f"📦 Lote: {lot_size}  🕒 {datetime.now().astimezone(colombia_tz).strftime('%H:%M:%S')}")
else:
    print(f"\n❌ Falló la ejecución de la orden:")
    print(f"🔁 Código: {result.retcode}")
    print(f"📄 Descripción: {result.comment}")

# === DESCONECTAR ===
mt5.shutdown()
