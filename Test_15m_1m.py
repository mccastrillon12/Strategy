import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timezone

symbol = "EURUSD"
risk_percent = 1  # % de riesgo por operación

# === CONEXIÓN A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

# === FUNCIONES ===
def detectar_pivotes():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 200)
    if rates is None or len(rates) < 3:
        return None, None
    df = pd.DataFrame(rates)
    piv_alto, piv_bajo = [], []
    for i in range(1, len(df) - 1):
        if df.loc[i, 'high'] > df.loc[i - 1, 'high'] and df.loc[i, 'high'] > df.loc[i + 1, 'high']:
            piv_alto.append(df.loc[i, 'high'])
        if df.loc[i, 'low'] < df.loc[i - 1, 'low'] and df.loc[i, 'low'] < df.loc[i + 1, 'low']:
            piv_bajo.append(df.loc[i, 'low'])
    if not piv_alto or not piv_bajo:
        return None, None
    return piv_alto[-1], piv_bajo[-1]

def calcular_lotes(sl_pips, balance, riesgo_pct):
    riesgo = balance * (riesgo_pct / 100)
    valor_pip = 10  # Asumiendo 1 lote estándar en EURUSD
    lotes = riesgo / (sl_pips * valor_pip)
    return round(lotes, 2)

def abrir_operacion(tipo, precio_entrada, sl, tp):
    account = mt5.account_info()
    if account is None:
        print("❌ No se pudo obtener información de la cuenta")
        return

    balance = account.balance
    sl_pips = abs(precio_entrada - sl)
    riesgo_usd = balance * (risk_percent / 100)
    valor_pip = 10  # Para 1 lote estándar EURUSD
    lotes_sugeridos = riesgo_usd / (sl_pips * valor_pip)

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print("❌ No se pudo obtener información del símbolo")
        return

    lote_min = symbol_info.volume_min
    lote_max = symbol_info.volume_max
    lote_step = symbol_info.volume_step

    # Redondear el lotaje al múltiplo válido más cercano hacia abajo
    lotes_ajustados = max(lote_min, min(lote_max, (lotes_sugeridos // lote_step) * lote_step))
    lotes_final = round(lotes_ajustados, 2)

    print(f"🔍 Lote sugerido: {lotes_sugeridos:.2f} | Ajustado: {lotes_final:.2f}")
    print(f"ℹ️ Límite del símbolo ➜ Min: {lote_min}, Max: {lote_max}, Step: {lote_step}")

    sl = round(sl, 5)
    tp = round(tp, 5)
    precio_entrada = round(precio_entrada, 5)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lotes_final,
        "type": mt5.ORDER_TYPE_BUY if tipo == "buy" else mt5.ORDER_TYPE_SELL,
        "price": mt5.symbol_info_tick(symbol).ask if tipo == "buy" else mt5.symbol_info_tick(symbol).bid,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": "Ruptura estructura",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Error al abrir orden: {result.retcode}")
    else:
        print(f"✅ Orden {tipo.upper()} enviada: Volumen {lotes_final} | SL: {sl} | TP: {tp}")

# === DETECCIÓN DE NIVELES ===
resistencia, soporte = detectar_pivotes()
if resistencia is None or soporte is None:
    mt5.shutdown()
    raise RuntimeError("❌ No se pudieron detectar los pivotes")

print(f"🟣 Niveles fijos ➜  Resistencia: {resistencia:.5f} | Soporte: {soporte:.5f}")

# === BANDERAS DE RUPTURA ===
rompimiento_alcista_detectado = False
rompimiento_bajista_detectado = False

# === BUCLE DE MONITOREO EN TIEMPO REAL ===
print("⏳ Esperando cierre de velas M1... (Ctrl+C para detener)")

try:
    ultimo_cierre_ts = None
    while True:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 1)
        if rates is None or len(rates) == 0:
            time.sleep(1)
            continue

        vela = rates[0]
        cierre_ts = vela['time']
        if cierre_ts == ultimo_cierre_ts:
            time.sleep(1)
            continue

        ultimo_cierre_ts = cierre_ts
        rango = vela['high'] - vela['low']
        cuerpo = abs(vela['close'] - vela['open'])
        cuerpo_alto = max(vela['open'], vela['close'])
        cuerpo_bajo = min(vela['open'], vela['close'])
        mitad_cuerpo = cuerpo * 0.5

        mecha_superior = vela['high'] - cuerpo_alto
        mecha_inferior = cuerpo_bajo - vela['low']

        hora_vela = datetime.fromtimestamp(cierre_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        if not rompimiento_alcista_detectado and vela['close'] > resistencia and (cuerpo_alto - resistencia) >= mitad_cuerpo:
            print(f"🚀 Ruptura ALCISTA | {hora_vela} UTC")
            print(f"🔎 Precio mecha superior: {vela['high']:.5f} | Cuerpo alto: {cuerpo_alto:.5f}")
            print(f"🔎 Precio mecha inferior: {vela['low']:.5f} | Cuerpo bajo: {cuerpo_bajo:.5f}")
            rompimiento_alcista_detectado = True
            sl = vela['low']
            tp = vela['close'] + (2 * abs(vela['close']) - sl)
            abrir_operacion("buy", vela['close'], sl, tp)

        elif not rompimiento_bajista_detectado and vela['close'] < soporte and (soporte - cuerpo_bajo) >= mitad_cuerpo:
            print(f"📉 Ruptura BAJISTA | {hora_vela} UTC")
            print(f"🔎 Precio mecha superior: {vela['high']:.5f} | Cuerpo alto: {cuerpo_alto:.5f}")
            print(f"🔎 Precio mecha inferior: {vela['low']:.5f} | Cuerpo bajo: {cuerpo_bajo:.5f}")
            
            rompimiento_bajista_detectado = True
            sl = vela['high']
            tp = vela['close'] - (2 * abs(sl - vela['close']))
            abrir_operacion("sell", vela['close'], sl, tp)

        # Si ya ocurrió una ruptura, salimos del bucle
        if rompimiento_alcista_detectado or rompimiento_bajista_detectado:
            break

        tiempo_restante = 60 - datetime.now(timezone.utc).second
        time.sleep(max(tiempo_restante, 1))

except KeyboardInterrupt:
    print("\n🛑 Monitoreo detenido por el usuario.")
finally:
    mt5.shutdown()
