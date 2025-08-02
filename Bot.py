import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import os

# === PARÁMETROS ===
symbol = "EURUSD"
initial_balance = 10000
risk_percent = 1
start_date = datetime.now() - timedelta(days=60)

# === CONECTAR A MT5 ===
if not mt5.initialize():
    raise RuntimeError("❌ No se pudo conectar a MT5")

# === CARGAR DATOS ===
rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_date, datetime.now())
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df['hora_col'] = df['time'].dt.tz_localize('UTC').dt.tz_convert('America/Bogota')

# Mostrar hora de la última vela
print(f"🕒 Última vela Colombia: {df['hora_col'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S')}")

# === RSI ===
df['rsi'] = RSIIndicator(close=df['close'], window=14).rsi()

# === DETECCIÓN DE PIN BARS ===
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

# === BACKTESTING ===
balance = initial_balance
wins = 0
losses = 0
results = []
capital = [initial_balance]
operaciones = []
operaciones_excel = []

for i in range(15, len(df) - 11):
    hora = df.iloc[i]['hora_col'].hour
    if not (8 <= hora <= 11):  # Horario Colombia
        continue

    row = df.iloc[i]
    rsi = row['rsi']
    entry = row['close']
    siguiente = df.iloc[i + 1]
    fecha_op = row['hora_col'].date()

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
    else:
        continue

    risk = initial_balance * (risk_percent / 100)
    reward = risk

    resultado = None
    for j in range(i + 2, i + 12):
        high = df.iloc[j]['high']
        low = df.iloc[j]['low']
        if direction == "buy":
            if low <= sl:
                resultado = -risk
                losses += 1
                break
            elif high >= tp:
                resultado = reward
                wins += 1
                break
        elif direction == "sell":
            if high >= sl:
                resultado = -risk
                losses += 1
                break
            elif low <= tp:
                resultado = reward
                wins += 1
                break

    if resultado is not None:
        balance += resultado
        results.append(resultado)
        capital.append(balance)
        operaciones.append((fecha_op, resultado))

        hora_ejecucion = row['hora_col']
        hora_cierre = df.iloc[j]['hora_col']
        operaciones_excel.append({
            "Fecha": fecha_op,
            "Hora entrada": hora_ejecucion.strftime('%H:%M:%S'),
            "Tipo": direction,
            "Precio entrada": round(entry, 5),
            "SL": round(sl, 5),
            "TP": round(tp, 5),
            "Resultado ($)": round(resultado, 2),
            "Hora cierre": hora_cierre.strftime('%H:%M:%S')
        })

# === RESULTADOS GENERALES ===
total_trades = wins + losses
winrate = (wins / total_trades) * 100 if total_trades > 0 else 0
ganancia_total = balance - initial_balance

print("\n📊 RESULTADOS BACKTEST (RSI + Pin Bar + Confirmación + Horario COL 8–11 a.m.)")
print(f"➤ Balance inicial: ${initial_balance}")
print(f"➤ Balance final:   ${round(balance, 2)}")
print(f"➤ Total operaciones: {total_trades}")
print(f"✔️ Ganadas: {wins} ❌ Perdidas: {losses}")
print(f"🎯 Winrate: {round(winrate, 2)}%")
print(f"💰 Ganancia neta: ${round(ganancia_total, 2)}")

# === RESUMEN DIARIO ===
df_op = pd.DataFrame(operaciones, columns=["fecha", "resultado"])

if not df_op.empty:
    dias = df_op.groupby("fecha")
    print("\n📅 Resumen diario de operaciones:\n")
    for fecha, grupo in dias:
        resumen = []
        total = 0
        for r in grupo["resultado"]:
            resumen.append("ganada" if r > 0 else "perdida")
            total += r
        print(f"{fecha.strftime('%d/%m/%y')} ➤ {' '.join(resumen)} = ${round(total, 2)}")

    perdida_por_dia = df_op.groupby("fecha")["resultado"].sum()
    dia_peor = perdida_por_dia.idxmin()
    perdida_max = perdida_por_dia.min()
    print(f"\n❌ Día con mayor pérdida: {dia_peor.strftime('%d/%m/%y')} ➤ Pérdida: ${round(perdida_max, 2)}")
else:
    print("⚠️ No se registraron operaciones válidas.")

# === GRAFICAR CAPITAL ===
plt.plot(capital)
plt.title("Evolución del capital")
plt.xlabel("Operaciones")
plt.ylabel("Balance ($)")
plt.grid(True)
plt.show()

# === EXPORTAR A EXCEL ===
ruta_excel = r"C:/Users/USUARIO/Desktop/Estrategia/operaciones_backtest.xlsx"

if operaciones_excel:
    try:
        df_excel = pd.DataFrame(operaciones_excel)
        df_excel.to_excel(ruta_excel, index=False)
        print(f"\n📁 Archivo Excel guardado correctamente en:\n{ruta_excel}")
    except Exception as e:
        print(f"❌ Error al guardar el archivo Excel: {e}")
else:
    print("⚠️ No hay operaciones para guardar en Excel.")

# === DESCONECTAR ===
mt5.shutdown()
