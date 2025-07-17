import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timezone

symbol = "EURUSD"

# === CONEXIÓN A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

# === FUNCIÓN PARA DETECTAR ÚLTIMO SOPORTE Y RESISTENCIA EN M1 ===
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

# === CALCULAR NIVELES UNA SOLA VEZ ===
resistencia, soporte = detectar_pivotes()
if resistencia is None or soporte is None:
    mt5.shutdown()
    raise RuntimeError("❌ No se pudieron detectar los pivotes")

print(f"🟣 Niveles fijos ➜  Resistencia: {resistencia:.5f} | Soporte: {soporte:.5f}")

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

        # Calcular y mostrar las mechas
        mecha_superior = vela['high'] - cuerpo_alto
        mecha_inferior = cuerpo_bajo - vela['low']
 

        hora_vela = datetime.fromtimestamp(cierre_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        # Validar ruptura con condición del 50% del cuerpo por fuera
        if vela['close'] > resistencia and (cuerpo_alto - resistencia) >= mitad_cuerpo:
            print(f"🚀 Ruptura ALCISTA | Vela cerró a las {hora_vela} UTC | Cuerpo por encima: {cuerpo_alto - resistencia:.5f} (≥ 50%)")
            print(f"🔎 Precio mecha superior: {vela['high']:.5f} | Cuerpo alto: {cuerpo_alto:.5f}")
            print(f"🔎 Precio mecha inferior: {vela['low']:.5f} | Cuerpo bajo: {cuerpo_bajo:.5f}")
        elif vela['close'] < soporte and (soporte - cuerpo_bajo) >= mitad_cuerpo:
            print(f"📉 Ruptura BAJISTA | Vela cerró a las {hora_vela} UTC | Cuerpo por debajo: {soporte - cuerpo_bajo:.5f} (≥ 50%)")
            print(f"🔎 Precio mecha superior: {vela['high']:.5f} | Cuerpo alto: {cuerpo_alto:.5f}")
            print(f"🔎 Precio mecha inferior: {vela['low']:.5f} | Cuerpo bajo: {cuerpo_bajo:.5f}")

        tiempo_restante = 60 - datetime.now(timezone.utc).second
        time.sleep(max(tiempo_restante, 1))

except KeyboardInterrupt:
    print("\n🛑 Monitoreo detenido por el usuario.")
finally:
    mt5.shutdown()