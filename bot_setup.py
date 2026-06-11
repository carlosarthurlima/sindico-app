import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from jobs import setup_jobs

logger = logging.getLogger(__name__)


def _chat_ids():
    raw = os.environ.get("ALLOWED_CHAT_IDS", "")
    return [int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]


def _autorizado(update: Update) -> bool:
    ids = _chat_ids()
    if not ids:
        return True
    uid = update.effective_user.id if update.effective_user else None
    cid = update.effective_chat.id if update.effective_chat else None
    return uid in ids or cid in ids


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    await update.message.reply_text(
        "🏢 *Síndico App Bot*\n\n"
        "Estou ativo e envio alertas automáticos:\n"
        "• ☀️ 08:30 — Relatório diário de demandas\n"
        "• 🔧 09:00 — Alertas de manutenções próximas\n"
        "• ⚠️ A cada 6h — Demandas com prazo vencendo\n\n"
        "Acesse o painel web para gerenciar.",
        parse_mode="Markdown",
    )


async def cmd_demandas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    import database as db
    from datetime import date
    demandas = db.listar_demandas(only_open=True)
    if not demandas:
        await update.message.reply_text("✅ Nenhuma demanda aberta no momento.")
        return
    por_cond: dict = {}
    for d in demandas:
        cond = (d.get("condominios") or {}).get("nome", "?")
        por_cond.setdefault(cond, []).append(d)
    linhas = [f"📋 *Demandas abertas — {len(demandas)} total*\n"]
    for cond, lista in sorted(por_cond.items()):
        linhas.append(f"🏢 *{cond}* ({len(lista)})")
        for d in lista:
            prazo = f" ⏰{d['data_limite']}" if d.get("data_limite") else ""
            linhas.append(f"  #{d['id']} {d['titulo'][:45]}{prazo}")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


async def cmd_manutencoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _autorizado(update):
        return
    import database as db
    from datetime import date
    itens = db.manutencoes_vencendo(dias=15)
    if not itens:
        await update.message.reply_text("✅ Nenhuma manutenção vencida ou próxima em 15 dias.")
        return
    hoje = date.today()
    linhas = [f"🔧 *Manutenções próximas/vencidas:*\n"]
    for m in itens:
        cond = (m.get("condominios") or {}).get("nome", "?")
        diff = (date.fromisoformat(m["data_vencimento"]) - hoje).days
        s = f"🔴 VENCIDA {abs(diff)}d" if diff < 0 else f"🟡 {diff}d"
        linhas.append(f"{s} — *{cond}*: {m['tipo']}")
    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


def build_bot() -> Application:
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("demandas",    cmd_demandas))
    app.add_handler(CommandHandler("manutencoes", cmd_manutencoes))
    setup_jobs(app)
    return app
