import time, random
from telebot import TeleBot
from utils.db import fetch_one, execute, execute_with_lastrowid
from utils.notify import log_admin

def _ensure_user(uid, uname):
    if fetch_one("SELECT 1 FROM users WHERE user_id=?", (uid,)) is None:
        execute("INSERT INTO users(user_id,username,balance) VALUES(?,?,0)", (uid, uname or ""))

def add_balance(uid, amount: float):
    execute("UPDATE users SET balance = COALESCE(balance,0)+? WHERE user_id=?", (float(amount), uid))

def get_balance(uid) -> float:
    row = fetch_one("SELECT balance FROM users WHERE user_id=?", (uid,))
    return float(row["balance"]) if row else 0.0

def register_balance(bot: TeleBot):
    @bot.message_handler(commands=['balance'])
    def balance_cmd(m):
        _ensure_user(m.from_user.id, m.from_user.username)
        bal = get_balance(m.from_user.id)
        bot.reply_to(m, f"💰 Ваш баланс: <b>{bal:.2f} ₽</b>", parse_mode="HTML")
