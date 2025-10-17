import os, json, time
from telebot import TeleBot
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))
PROMO_FILE = os.getenv("PROMO_FILE", "promos.json")
def _now(): return int(time.time())
def _load():
    try: return json.loads(open(PROMO_FILE,'r',encoding='utf-8').read())
    except: return {}
def _save(d):
    try: open(PROMO_FILE,'w',encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2))
    except: pass
def _check(code, user_id):
    d = _load(); p = d.get(code.upper())
    if not p: return (False, "Промокод не найден")
    if p.get("expires") and _now() > int(p["expires"]): return (False, "Срок действия промокода истёк")
    if p.get("usage_limit") and p.get("used_total",0) >= int(p["usage_limit"]): return (False, "Промокод более недоступен")
    if p.get("per_user",0)>0:
        used_times = sum(1 for u in p.get("used_users",[]) if u==user_id)
        if used_times >= int(p["per_user"]): return (False, "Вы уже использовали этот промокод")
    return (True, p)
def apply_code(code, user_id):
    ok,res = _check(code,user_id)
    if not ok: return (False,res)
    d=_load(); p=d[code.upper()]; p["used_total"]=p.get("used_total",0)+1; p.setdefault("used_users",[]).append(user_id); _save(d)
    return (True, float(p.get("factor",1.0)))
def register_promos(bot: TeleBot):
    @bot.message_handler(commands=['promo_list'])
    def promo_list(m):
        if m.from_user.id != ADMIN_ID: return
        d=_load()
        if not d: bot.reply_to(m,"Промокодов нет."); return
        lines=[]; 
        for k,v in d.items():
            exp=v.get("expires",0); till=f"{exp} (unix)" if exp else "∞"
            lines.append(f"{k}: x{v.get('factor',1.0)}, до: {till}, всего: {v.get('usage_limit','∞')}, использовано: {v.get('used_total',0)}, на пользователя: {v.get('per_user',0)}")
        bot.reply_to(m, "\n".join(lines))
    @bot.message_handler(commands=['promo_add'])
    def promo_add(m):
        if m.from_user.id != ADMIN_ID: return
        parts=(m.text or "").split()
        if len(parts)<3: bot.reply_to(m,"Формат: /promo_add CODE factor [days] [usage_limit] [per_user]"); return
        code=parts[1].upper(); factor=float(parts[2])
        days=int(parts[3]) if len(parts)>=4 else 0
        usage=int(parts[4]) if len(parts)>=5 else 0
        per_user=int(parts[5]) if len(parts)>=6 else 1
        exp=_now()+days*86400 if days>0 else 0
        d=_load(); d[code]={"factor":factor,"expires":exp,"usage_limit":usage,"used_total":0,"per_user":per_user,"used_users":[]}; _save(d)
        bot.reply_to(m, f"✅ Добавлен {code}: x{factor}, дней: {days or '∞'}, лимит: {usage or '∞'}, на пользователя: {per_user}")
    @bot.message_handler(commands=['promo_del'])
    def promo_del(m):
        if m.from_user.id != ADMIN_ID: return
        parts=(m.text or "").split()
        if len(parts)!=2: bot.reply_to(m,"Формат: /promo_del CODE"); return
        code=parts[1].upper(); d=_load()
        if code in d: del d[code]; _save(d); bot.reply_to(m, f"🗑 Удалён {code}")
        else: bot.reply_to(m,"Код не найден.")
    @bot.message_handler(commands=['promo_check'])
    def promo_check(m):
        parts=(m.text or "").split()
        if len(parts)!=2: bot.reply_to(m,"Формат: /promo_check CODE"); return
        ok,res=_check(parts[1], m.from_user.id)
        if ok: bot.reply_to(m, f"✅ Промокод действует: множитель x{res.get('factor',1.0)}")
        else: bot.reply_to(m, f"❌ {res}")
