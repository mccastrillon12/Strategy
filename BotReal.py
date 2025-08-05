import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import smtplib
from email.message import EmailMessage
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta
import pytz
import time

# === PARÁMETROS ===
symbol = "EURUSD"
risk_percent = 0.5
timezone = pytz.timezone("America/Bogota")

# === DATOS EMAIL ===
EMAIL_FROM = "castrillonosorio12@gmail.com"
EMAIL_TO = "castrillonosorio12@gmail.com"
EMAIL_PASS = "qknwerxaoalerbtn"

# === FUNCIÓN ENVÍO DE CORREO ===
def enviar_correo(asunto, mensaje):
    try:
        msg = EmailMessage()
        msg.set_content(mensaje)
        msg["Subject"] = asunto
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_FROM, EMAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        print(f"❌ Error enviando email: {e}")

# === CONEXIÓN A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

account_info = mt5.account_info()
if account_info is None:
    raise RuntimeError("❌ No se pudo obtener información de cuenta")

print(f"💼 Balance actual: ${account_info.balance:.2f}")

# === CICLO PRINCIPAL EN TIEMPO REAL ===
franja_abierta = False
ultima_hora_impresa = None

while True:
    ahora = datetime.now(timezone)
    hora_actual = ahora.hour

    if hora_actual < 8 or hora_actual > 11:
        if franja_abierta:
            print("🕒 Franja de operación Cerrada")
            franja_abierta = False
        if ultima_hora_impresa != hora_actual:
            print("⛔ Mercado cerrado para operaciones")
            ultima_hora_impresa = hora_actual
        time.sleep(60)
        continue
    elif not franja_abierta:
        print("✅ Franja de operación Abierta")
        franja_abierta = True

    # === OBTENER ÚLTIMAS 100 VELAS ===
    utc_from = datetime.utcnow() - timedelta(minutes=100)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, utc_from, datetime.utcnow())
    df = pd.DataFrame(rates)
    if df.empty or len(df) < 15:
        time.sleep(60)
        continue

    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['hora_col'] = df['time'].dt.tz_localize('UTC').dt.tz_convert('America/Bogota')
    df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()

    # === CONDICIONES DE ENTRADA ===
    i = len(df) - 2
    row = df.iloc[i]
    siguiente = df.iloc[i + 1]

    def es_pin_bar_bullish(row):
        cuerpo = abs(row['close'] - row['open'])
        mecha_inferior = row['open'] - row['low'] if row['close'] > row['open'] else row['close'] - row['low']
        mecha_superior = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        return mecha_inferior > 2 * cuerpo and mecha_inferior > mecha_superior

    def es_pin_bar_bearish(row):
        cuerpo = abs(row['close'] - row['open'])
        mecha_superior = row['high'] - row['open'] if row['close'] < row['open'] else row['high'] - row['close']
        mecha_inferior = row['open'] - row['low'] if row['close'] < row['open'] else row['close'] - row['low']
        return mecha_superior > 2 * cuerpo and mecha_superior > mecha_inferior

    rsi = row['rsi']
    entry = row['close']
    direction = None

    if rsi < 30 and es_pin_bar_bullish(row) and siguiente['close'] > siguiente['open']:
        sl = row['low']
        sl_distance = entry - sl
        tp = entry + sl_distance
        direction = "buy"
    elif rsi > 70 and es_pin_bar_bearish(row) and siguiente['close'] < siguiente['open']:
        sl = row['high']
        sl_distance = sl - entry
        tp = entry - sl_distance
        direction = "sell"

    if direction is None or sl_distance <= 0:
        time.sleep(30)
        continue

    # === INFO DEL SÍMBOLO ===
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        enviar_correo("⛔ Error", f"No se pudo obtener información del símbolo {symbol}")
        time.sleep(60)
        continue

    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max
    volume_step = symbol_info.volume_step

    # === CÁLCULO DEL LOTE CON AJUSTES ===
    balance_actual = mt5.account_info().balance
    riesgo = balance_actual * (risk_percent / 100)
    raw_lot = riesgo / sl_distance

    # Redondear al step permitido
    pasos = round(raw_lot / volume_step)
    lot_size = round(pasos * volume_step, 2)

    # Validar límites
    if lot_size < volume_min:
        enviar_correo("⛔ Operación NO ejecutada", f"Lotaje calculado ({lot_size}) es menor al mínimo permitido ({volume_min})")
        time.sleep(60)
        continue
    elif lot_size > volume_max:
        lot_size = round(volume_max, 2)
        enviar_correo("⚠️ Lotaje ajustado", f"Lotaje calculado era demasiado alto. Se ajustó a máximo permitido: {lot_size}")

    # === CREAR ORDEN ===
    ticket = int(datetime.timestamp(datetime.now()))

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
        "price": mt5.symbol_info_tick(symbol).ask if direction == "buy" else mt5.symbol_info_tick(symbol).bid,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "deviation": 10,
        "magic": ticket,
        "comment": "RSI + Pin Bar + Confirmación",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        error_msg = f"❌ Error al ejecutar operación: {result.comment}"
        print(error_msg)
        enviar_correo("⛔ Operación NO ejecutada", error_msg)
    else:
        operacion_msg = f"""✅ OPERACIÓN EJECUTADA
Tipo: {direction.upper()}
Precio entrada: {entry}
SL: {round(sl, 5)}
TP: {round(tp, 5)}
Lotaje: {lot_size}
Balance actual: ${balance_actual:.2f}
Hora ejecución: {ahora.strftime('%H:%M:%S')} (Col)
"""
        print(operacion_msg)
        enviar_correo("✅ Operación ejecutada", operacion_msg)

    # Esperar antes de evaluar de nuevo
    time.sleep(60)
