import os
from datetime import date, datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client = None

CONDOMINIOS_INICIAIS = [
    "Vale do Paraíba", "Palmeiras Prime 2", "Essenza", "Pericumã",
    "University Home", "Monte Carlo", "Belvedere", "Portal das Gaivotas",
    "Marília 2", "Coronel Onofre", "Yagua", "Munim",
]

STATUS_KANBAN = [
    ("novo",          "Novo",          "secondary"),
    ("em_cotacao",    "Em Cotação",    "warning"),
    ("aprovado",      "Aprovado",      "info"),
    ("em_execucao",   "Em Execução",   "primary"),
    ("concluido",     "Concluído",     "success"),
]
STATUS_ABERTOS  = ["novo", "em_cotacao", "aprovado", "em_execucao"]
STATUS_FECHADOS = ["concluido", "cancelado"]

CATEGORIAS = ["elétrica", "hidráulica", "pintura", "estrutural",
              "segurança", "limpeza", "jardim", "compras", "outros"]

DIAS_ALERTA_DEMANDA    = 3
DIAS_ALERTA_MANUTENCAO = 15


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ─── Condomínios ──────────────────────────────────────────────────────────────

def listar_condominios(only_active=True):
    db = get_db()
    q = db.table("condominios").select("*").order("nome")
    if only_active:
        q = q.eq("ativo", True)
    return q.execute().data


def get_condominio(cond_id: str):
    return get_db().table("condominios").select("*").eq("id", cond_id).single().execute().data


def criar_condominio(nome, endereco="", responsavel="", telefone=""):
    return get_db().table("condominios").insert({
        "nome": nome, "endereco": endereco,
        "responsavel": responsavel, "telefone": telefone,
    }).execute().data


def atualizar_condominio(cond_id, **fields):
    get_db().table("condominios").update(fields).eq("id", cond_id).execute()


def desativar_condominio(cond_id):
    get_db().table("condominios").update({"ativo": False}).eq("id", cond_id).execute()


# ─── Demandas ─────────────────────────────────────────────────────────────────

def listar_demandas(condominio_id=None, status=None, only_open=False):
    db = get_db()
    q = db.table("demandas").select("*, condominios(nome)").order("criado_em", desc=True)
    if condominio_id:
        q = q.eq("condominio_id", condominio_id)
    if status:
        q = q.eq("status", status)
    if only_open:
        q = q.in_("status", STATUS_ABERTOS)
    return q.execute().data


def get_demanda(dem_id: int):
    return get_db().table("demandas").select("*, condominios(nome)").eq("id", dem_id).single().execute().data


def criar_demanda(condominio_id, titulo, descricao="", categoria="outros",
                  prestador="", valor=None, data_limite=None):
    return get_db().table("demandas").insert({
        "condominio_id": condominio_id, "titulo": titulo,
        "descricao": descricao, "categoria": categoria,
        "prestador": prestador or None, "valor": valor,
        "data_limite": data_limite,
    }).execute().data


def atualizar_demanda_status(dem_id: int, status: str):
    get_db().table("demandas").update({
        "status": status,
        "atualizado_em": datetime.now().isoformat(),
    }).eq("id", dem_id).execute()


def atualizar_demanda(dem_id: int, **fields):
    fields["atualizado_em"] = datetime.now().isoformat()
    get_db().table("demandas").update(fields).eq("id", dem_id).execute()


def excluir_demanda(dem_id: int):
    get_db().table("demandas").delete().eq("id", dem_id).execute()


def demandas_vencendo(dias=DIAS_ALERTA_DEMANDA):
    """Demandas abertas com data_limite <= hoje + dias dias."""
    db = get_db()
    hoje = date.today().isoformat()
    limite = date.today().replace(
        day=min(date.today().day + dias, 28)
    ).isoformat()
    # Use range filter: data_limite between hoje and hoje+dias
    rows = db.table("demandas").select("*, condominios(nome)") \
        .in_("status", STATUS_ABERTOS) \
        .not_.is_("data_limite", "null") \
        .lte("data_limite", limite) \
        .execute().data
    return rows


def marcar_alerta_demanda(dem_id: int):
    get_db().table("demandas").update({
        "alerta_enviado_em": datetime.now().isoformat()
    }).eq("id", dem_id).execute()


# ─── Manutenções ──────────────────────────────────────────────────────────────

def listar_manutencoes(condominio_id=None):
    db = get_db()
    q = db.table("manutencoes").select("*, condominios(nome)").order("data_vencimento")
    if condominio_id:
        q = q.eq("condominio_id", condominio_id)
    return q.execute().data


def get_manutencao(manut_id: int):
    return get_db().table("manutencoes").select("*, condominios(nome)").eq("id", manut_id).single().execute().data


def criar_manutencao(condominio_id, tipo, data_vencimento, descricao="",
                     prestador="", data_realizacao=None, valor=None, observacoes=""):
    return get_db().table("manutencoes").insert({
        "condominio_id": condominio_id, "tipo": tipo,
        "descricao": descricao or None, "prestador": prestador or None,
        "data_realizacao": data_realizacao, "data_vencimento": data_vencimento,
        "valor": valor, "observacoes": observacoes or None,
    }).execute().data


def atualizar_manutencao(manut_id: int, **fields):
    get_db().table("manutencoes").update(fields).eq("id", manut_id).execute()


def excluir_manutencao(manut_id: int):
    get_db().table("manutencoes").delete().eq("id", manut_id).execute()


def manutencoes_vencendo(dias=DIAS_ALERTA_MANUTENCAO):
    """Manutenções com data_vencimento <= hoje + dias dias."""
    import calendar
    hoje = date.today()
    mes = hoje.month + (dias // 30)
    ano = hoje.year + (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    limite = hoje.replace(
        year=ano, month=mes,
        day=min(hoje.day, calendar.monthrange(ano, mes)[1])
    ).isoformat()
    rows = get_db().table("manutencoes").select("*, condominios(nome)") \
        .lte("data_vencimento", limite) \
        .execute().data
    return rows


def marcar_alerta_manutencao(manut_id: int):
    get_db().table("manutencoes").update({
        "alerta_enviado_em": datetime.now().isoformat()
    }).eq("id", manut_id).execute()
