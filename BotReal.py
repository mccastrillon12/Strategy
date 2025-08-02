import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
from ta.momentum import RSIIndicator
import time

# === PARÁMETROS ===
symbol = "EURUSD"
risk_percent = 1
magic_number = 123456
lot_min = 0.01
slippage = 10
timezone_offset = -4  # NY

# === CONECTAR A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

# === CALCULAR LOTE POR RIESGO ===
def calcular_lote(riesgo_usd, sl_pips):
    tick_size = mt5.symbol_info(symbol).point
    lot_step = mt5.symbol_info(symbol).volume_step
    tick_value = mt5.symbol_info(symbol).trade_tick_value
    if sl_pips == 0 or tick_value == 0:
        return lot_min
    lot = riesgo_usd / (sl_pips / 10 * tick_value)
    return max(round(lot / lot_step) * lot_step, lot_min)

# === VERIFICAR OPERACIÓN ACTIVA ===
def hay_operacion_abierta():
    positions = mt5.positions_get(symbol=symbol)
    return len(positions) > 0

# === DETECTAR PIN BARS ===
def es_pin_bar_bullish(row):
    cuerpo = abs(row['close'] - row['open'])
    mecha_inf = row['open'] - row['low'] if row['close'] > row['open'] else row['close'] - row['low']
    mecha_sup = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
    return mecha_inf > 2 * cuerpo and mecha_inf > mecha_sup

def es_pin_bar_bearish(row):
    cuerpo = abs(row['close'] - row['open'])
    mecha_sup = row['high'] - row['open'] if row['close'] < row['open'] else row['high'] - row['close']
    mecha_inf = row['open'] - row['low'] if row['close'] < row['open'] else row['close'] - row['low']
    return mecha_sup > 2 * cuerpo and mecha_sup > mecha_inf

# === LOOP DE ESCANEO CONTINUO ===
print("🚀 Bot iniciado. Esperando señales...\n")
ultima_vela = None

while True:
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    hora_ny = (now.hour + timezone_offset) % 24
    if hora_ny < 8 or hora_ny > 11:
        time.sleep(30)
        continue

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 20)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()

    row = df.iloc[-3]  # vela 3era desde el final (cierre confirmado)
    siguiente = df.iloc[-2]  # vela siguiente a la señal
    actual = df.iloc[-1]  # vela actual

    # Evitar ejecutar doble señal sobre misma vela
    if ultima_vela == row['time']:
        time.sleep(10)
        continue
    ultima_vela = row['time']

    entry_price = row['close']
    balance = mt5.account_info().balance
    riesgo_usd = balance * (risk_percent / 100)

    # Señal de compra
    if row['rsi'] < 30 and es_pin_bar_bullish(row) and siguiente['close'] > siguiente['open']:
        sl = row['low']
        sl_pips = (entry_price - sl) / mt5.symbol_info(symbol).point
        tp = entry_price + (entry_price - sl)
        lot = calcular_lote(riesgo_usd, sl_pips)
        if not hay_operacion_abierta():
            print(f"🟢 COMPRA {symbol} @ {entry_price} | SL: {sl} | TP: {tp} | Lote: {lot}")
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_BUY,
                "price": mt5.symbol_info_tick(symbol).ask,
                "sl": sl,
                "tp": tp,
                "deviation": slippage,
                "magic": magic_number,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })

    # Señal de venta
    elif row['rsi'] > 70 and es_pin_bar_bearish(row) and siguiente['close'] < siguiente['open']:
        sl = row['high']
        sl_pips = (sl - entry_price) / mt5.symbol_info(symbol).point
        tp = entry_price - (sl - entry_price)
        lot = calcular_lote(riesgo_usd, sl_pips)
        if not hay_operacion_abierta():
            print(f"🔴 VENTA {symbol} @ {entry_price} | SL: {sl} | TP: {tp} | Lote: {lot}")
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_SELL,
                "price": mt5.symbol_info_tick(symbol).bid,
                "sl": sl,
                "tp": tp,
                "deviation": slippage,
                "magic": magic_number,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })

    time.sleep(10)  # esperar a que cierre nueva vela
