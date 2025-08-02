from telethon.sync import TelegramClient
import re

# === CONFIGURACIÓN ===
api_id = 29633269
api_hash = '5c2a5c15e5e7b142d04768b6ae03e974'
group_username = 'GoldTraderMe'

# === CONEXIÓN A TELEGRAM ===
client = TelegramClient('session_name', api_id, api_hash)

with client:
    valid_signals = []  # Lista para guardar señales válidas

    # Buscar hasta 100 mensajes para encontrar 10 válidos
    for message in client.iter_messages(group_username, limit=100):
        texto = message.message
        if texto is None:
            continue

        # Buscar estructura de señal
        indice = re.search(r'([A-Z0-9]+)\s+(BUY|SELL)', texto, re.IGNORECASE)
        entry = re.search(r'ENTRY\s+(\d+)', texto)
        sl = re.search(r'SL\s+(\d+)', texto)
        tps = re.findall(r'TP\s+(\d+)', texto)

        if indice and entry and sl and len(tps) >= 2:
            valid_signals.append({
                'indice': indice.group(1).upper(),
                'tipo': indice.group(2).upper(),
                'entry': entry.group(1),
                'sl': sl.group(1),
                'tp1': tps[0],
                'tp2': tps[1],
                'date': message.date
            })

            if len(valid_signals) == 1:
                break

    # Mostrar de la más antigua a la más reciente
    valid_signals.reverse()

    for i, signal in enumerate(valid_signals, 1):
        print(f"\n📥 Señal #{i}")
        print("Fecha:", signal['date'])
        print("Índice:", signal['indice'])
        print("Tipo:", signal['tipo'])
        print("ENTRY:", signal['entry'])
        print("SL:", signal['sl'])
        print("TP1:", signal['tp1'])
        print("TP2:", signal['tp2'])
