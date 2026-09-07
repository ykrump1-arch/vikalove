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

# Комплимент дня: во сколько присылать (часы:минуты).
DAILY_TIME = "09:00"

# Часовой пояс, в котором указано время выше. Ташкент = 5 (UTC+5).
# Нужно потому, что сервер хостинга обычно живёт по UTC.
TZ_OFFSET_HOURS = 5

# Файл, где бот запоминает, кому слать комплимент дня и что уже присылал.
# На Railway путь задаётся переменной STATE_FILE (например /data/state.json),
# чтобы память не терялась при перезапуске.
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
    return {"daily": [], "used": {}, "last_daily": ""}


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
    """Достаёт комплимент, который этому чату ещё не приходил.
    Когда все 500 закончатся — список начинается заново."""
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
    # если комплимент начинается с обращения — делаем первую букву заглавной
    if text.startswith("{n}"):
        name = name[0].upper() + name[1:]
    return text.replace("{n}", name)


def keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("💛 Комплимент"))
    kb.add(types.KeyboardButton("☀️ Комплимент дня: вкл/выкл"))
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
        "/daily — включить или выключить комплимент дня\n"
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
        bot.send_message(chat_id, f"Готово, буду писать каждый день в {DAILY_TIME} ☀️")
    else:
        bot.send_message(chat_id, "Хорошо, комплимент дня выключен.")


@bot.message_handler(func=lambda m: True)
def any_message(message):
    if message.text and "Комплимент дня" in message.text:
        toggle_daily(message.chat.id)
        return
    bot.send_message(message.chat.id, make_compliment(message.chat.id),
                     reply_markup=keyboard())


def local_now():
    """Текущее время в твоём часовом поясе."""
    return datetime.utcnow() + timedelta(hours=TZ_OFFSET_HOURS)


def daily_loop():
    """Раз в 30 секунд проверяет время и рассылает комплимент дня."""
    while True:
        try:
            now = local_now().strftime("%H:%M")
            today = local_now().strftime("%Y-%m-%d")
            if now == DAILY_TIME and STATE.get("last_daily") != today:
                for chat_id in list(STATE["daily"]):
                    try:
                        bot.send_message(chat_id, "☀️ " + make_compliment(chat_id))
                    except Exception as e:
                        print("не смог отправить:", e)
                with _lock:
                    STATE["last_daily"] = today
                    save_state(STATE)
        except Exception as e:
            print("ошибка в рассылке:", e)
        time.sleep(30)


class PingHandler(BaseHTTPRequestHandler):
    """Крошечная веб-страничка. Нужна только для хостингов вроде Render:
    они требуют, чтобы приложение слушало порт, и «будят» его по запросу."""

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
        return  # локально веб-сервер не нужен
    HTTPServer(("0.0.0.0", int(port)), PingHandler).serve_forever()


if __name__ == "__main__":
    print(f"Бот запущен. Комплиментов: {len(COMPLIMENTS)}, обращений: {len(NAMES)}")
    threading.Thread(target=daily_loop, daemon=True).start()
    threading.Thread(target=start_web_server, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
