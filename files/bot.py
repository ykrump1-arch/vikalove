# -*- coding: utf-8 -*-
"""
Бот с комплиментами для Виктории.
Запуск:  python bot.py
Нужен файл compliments.py рядом.
"""

import json
import os
import random
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from telebot import types

from compliments import COMPLIMENTS, NAMES

# ─────────────────────────────────────────────
#  НАСТРОЙКИ — тут меняешь всё под себя
# ─────────────────────────────────────────────

# Токен от @BotFather. Вставь его сюда между кавычками.
TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН")

# Как часто присылать комплименты, в часах. Поставь 2 или 3 — как захочешь.
EVERY_HOURS = 3

# Дневное окно: с какого часа начинать и до какого можно писать.
# 9 и 24 значит "с девяти утра и до полуночи", ночью бот молчит.
DAY_START_HOUR = 9
DAY_END_HOUR = 24

# Часовой пояс, в котором указано время выше. Ташкент = 5 (UTC+5).
TZ_OFFSET_HOURS = 5

# Файл, где бот хранит память. На Railway задаётся переменной STATE_FILE.
STATE_FILE = os.environ.get("STATE_FILE", "state.json")

# ─────────────────────────────────────────────

bot = telebot.TeleBot(TOKEN)
_lock = threading.Lock()


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"daily": [], "used": {}, "sent": []}


def save_state(state):
    try:
        folder = os.path.dirname(STATE_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        print("не смог сохранить память:", e)


STATE = load_state()


def make_compliment(chat_id):
    """Достаёт комплимент, который этому чату ещё не приходил."""
    chat_id = str(chat_id)
    with _lock:
        used = set(STATE["used"].get(chat_id, []))
        if len(used) >= len(COMPLIMENTS):
            used = set()
        free = [i for i in range(len(COMPLIMENTS)) if i not in used]
        idx = random.choice(free)
        used.add(idx)
        STATE["used"][chat_id] = list(used)
        save_state(STATE)

    name = random.choice(NAMES)
    text = COMPLIMENTS[idx]
    if text.startswith("{n}"):
        name = name[0].upper() + name[1:]
    return text.replace("{n}", name)


def keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("💛 Комплимент"))
    kb.add(types.KeyboardButton("☀️ Комплименты по расписанию"))
    return kb


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет, красотулечка 💛\n\n"
        "Я умею говорить приятные вещи. Жми кнопку — и получай комплимент.\n"
        f"Их у меня {len(COMPLIMENTS)}, повторяться не буду.",
        reply_markup=keyboard(),
    )
    bot.send_message(message.chat.id, make_compliment(message.chat.id))


@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(
        message.chat.id,
        "Просто напиши что угодно или нажми кнопку — пришлю комплимент.\n"
        "/daily — включить или выключить комплименты по расписанию\n"
        "/reset — обнулить историю, чтобы всё пошло по новой",
        reply_markup=keyboard(),
    )


@bot.message_handler(commands=["reset"])
def reset(message):
    with _lock:
        STATE["used"].pop(str(message.chat.id), None)
        save_state(STATE)
    bot.send_message(message.chat.id, "Начинаем заново 💛", reply_markup=keyboard())


@bot.message_handler(commands=["daily"])
def daily_cmd(message):
    toggle_daily(message.chat.id)


def toggle_daily(chat_id):
    with _lock:
        if chat_id in STATE["daily"]:
            STATE["daily"].remove(chat_id)
            on = False
        else:
            STATE["daily"].append(chat_id)
            on = True
        save_state(STATE)
    if on:
        hours = ", ".join(f"{h:02d}:00" for h in schedule_times())
        bot.send_message(
            chat_id,
            f"Готово ☀️ Буду писать каждые {EVERY_HOURS} ч: {hours}.\nНочью не бужу.",
        )
    else:
        bot.send_message(chat_id, "Хорошо, по расписанию больше не пишу.")


@bot.message_handler(func=lambda m: True)
def any_message(message):
    if message.text and "по расписанию" in message.text:
        toggle_daily(message.chat.id)
        return
    bot.send_message(message.chat.id, make_compliment(message.chat.id),
                     reply_markup=keyboard())


def schedule_times():
    """Список часов, в которые бот пишет. Например [9, 12, 15, 18, 21]."""
    return list(range(DAY_START_HOUR, DAY_END_HOUR, EVERY_HOURS))


def local_now():
    """Текущее время в твоём часовом поясе."""
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET_HOURS)


def schedule_loop():
    """Раз в минуту проверяет: не пора ли отправить очередной комплимент."""
    while True:
        try:
            now = local_now()
            for hour in schedule_times():
                if now.hour != hour or now.minute >= 10:
                    continue
                slot = now.strftime("%Y-%m-%d ") + str(hour)
                if slot in STATE.get("sent", []):
                    continue
                for chat_id in list(STATE["daily"]):
                    try:
                        bot.send_message(chat_id, make_compliment(chat_id))
                    except Exception as e:
                        print("не смог отправить:", e)
                with _lock:
                    STATE.setdefault("sent", []).append(slot)
                    STATE["sent"] = STATE["sent"][-30:]
                    save_state(STATE)
        except Exception as e:
            print("ошибка в расписании:", e)
        time.sleep(60)


class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Бот жив и полон комплиментов 💛".encode("utf-8"))

    def log_message(self, *args):
        pass


def start_web_server():
    port = os.environ.get("PORT")
    if not port:
        return
    HTTPServer(("0.0.0.0", int(port)), PingHandler).serve_forever()


if __name__ == "__main__":
    print(f"Бот запущен. Комплиментов: {len(COMPLIMENTS)}, обращений: {len(NAMES)}")
    print("Расписание:", ", ".join(f"{h:02d}:00" for h in schedule_times()))
    threading.Thread(target=schedule_loop, daemon=True).start()
    threading.Thread(target=start_web_server, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
