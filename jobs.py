import os
import logging
from datetime import date, time
import pytz
import database as db

logger = logging.getLogger(__name__)
TZ = pytz.timezone(os.environ.get("TZ", "America/Sao_Paulo"))


def _chat_ids():
    raw = os.environ.get("ALLOWED_CHAT_IDS", "")
    return [int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]


async def _send(context, text: str):
    for cid in _chat_ids():
        try:
            await context.bot.send_message(chat_id=cid, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Erro ao enviar para %s: %s", cid, e)


# ─── Relatório diário 08:30 ───────────────────────────────────────────────────

async def daily_report(context):
    hoje = date.today()
    demandas = db.listar_demandas(only_open=True)
    manuts   = db.manutencoes_vencendo(dias=db.DIAS_ALERTA_MANUTENCAO)

    linhas = [f"☀️ *Relatório Diário — {hoje}*\n"]
    linhas.append(f"📋 Demandas abertas: *{len(demandas)}*")
    linhas.append(f"🔧 Manutenções próximas/vencidas: *{len(manuts)}*\n")

    if demandas:
        # Group by condominium
        por_cond: dict = {}
        for d in demandas:
            cond = (d.get("condominios") or {}).get("nome", "?")
            por_cond.setdefault(cond, []).append(d)

        STATUS_EMOJI = {
            "novo": "🔴", "em_cotacao": "🟡",
            "aprovado": "🟢", "em_execucao": "🔵",
        }
        linhas.append("*📊 Demandas abertas por condomínio:*")
        for cond_nome, lista in sorted(por_cond.items()):
            linhas.append(f"\n🏢 *{cond_nome}* ({len(lista)})")
            for d in lista:
                emoji = STATUS_EMOJI.get(d["status"], "⚪")
                prazo = f" ⏰ {d['data_limite']}" if d.get("data_limite") else ""
                titulo = d["titulo"][:45]
                linhas.append(f"  {emoji} #{d['id']} {titulo}{prazo}")

    if manuts:
        linhas.append(f"\n*🔧 Manutenções que precisam de atenção:*")
        for m in manuts:
            cond = (m.get("condominios") or {}).get("nome", "?")
            diff = (date.fromisoformat(m["data_vencimento"]) - hoje).days
            if diff < 0:
                s = f"🔴 VENCIDA há {abs(diff)}d"
            else:
                s = f"🟡 Vence em {diff}d"
            linhas.append(f"  {s} — {cond}: {m['tipo']}")

    linhas.append("\n🔗 Acesse o painel para gerenciar.")
    await _send(context, "\n".join(linhas))


# ─── Alerta de demanda próxima do prazo ───────────────────────────────────────

async def alert_demandas(context):
    demandas = db.demandas_vencendo(dias=db.DIAS_ALERTA_DEMANDA)
    novas = [d for d in demandas if not d.get("alerta_enviado_em")]
    if not novas:
        return

    linhas = [f"⚠️ *Demandas próximas do prazo ({len(novas)}):*\n"]
    for d in novas:
        cond = (d.get("condominios") or {}).get("nome", "?")
        diff = (date.fromisoformat(d["data_limite"]) - date.today()).days
        if diff < 0:
            s = f"🔴 VENCIDA há {abs(diff)} dia(s)"
        else:
            s = f"🟡 Vence em {diff} dia(s)"
        linhas.append(f"🏢 *{cond}* — #{d['id']} {d['titulo'][:45]}\n   {s}\n")

    linhas.append("Acesse o painel para atualizar o status.")
    await _send(context, "\n".join(linhas))
    for d in novas:
        db.marcar_alerta_demanda(d["id"])


# ─── Alerta de manutenção vencendo ────────────────────────────────────────────

async def alert_manutencoes(context):
    manuts = db.manutencoes_vencendo(dias=db.DIAS_ALERTA_MANUTENCAO)
    novas  = [m for m in manuts if not m.get("alerta_enviado_em")]
    if not novas:
        return

    hoje = date.today()
    linhas = [f"🔧 *Alerta de Manutenção ({len(novas)} item(ns)):*\n"]
    for m in novas:
        cond = (m.get("condominios") or {}).get("nome", "?")
        diff = (date.fromisoformat(m["data_vencimento"]) - hoje).days
        if diff < 0:
            s = f"🔴 VENCIDA há {abs(diff)} dias"
        else:
            s = f"🟡 Vence em {diff} dias ({m['data_vencimento']})"
        prestador = f"\n   👷 {m['prestador']}" if m.get("prestador") else ""
        linhas.append(f"🏢 *{cond}*\n   {m['tipo']}: {s}{prestador}\n")

    linhas.append("Acesse o painel para renovar.")
    await _send(context, "\n".join(linhas))
    for m in novas:
        db.marcar_alerta_manutencao(m["id"])


# ─── Registro ─────────────────────────────────────────────────────────────────

def setup_jobs(app):
    jq = app.job_queue
    jq.run_daily(daily_report,   time=time(8, 30, tzinfo=TZ), name="daily_report")
    jq.run_daily(alert_manutencoes, time=time(9, 0, tzinfo=TZ), name="alert_manut")
    jq.run_repeating(alert_demandas, interval=3600*6, first=120, name="alert_demandas")
    logger.info("Jobs agendados: daily_report(08:30), alert_manut(09:00), alert_demandas(6h)")
