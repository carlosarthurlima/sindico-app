import os
import io
from datetime import date, datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import database as db

app = FastAPI(title="Síndico App")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

SQL_SETUP = """-- Cole este SQL no Supabase SQL Editor e clique em RUN
-- https://supabase.com/dashboard/project/kpfiweztwsiwcbsvdvbi/sql

CREATE TABLE IF NOT EXISTS condominios (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome        TEXT NOT NULL UNIQUE,
    endereco    TEXT,
    responsavel TEXT,
    telefone    TEXT,
    ativo       BOOLEAN DEFAULT true,
    criado_em   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS demandas (
    id             BIGSERIAL PRIMARY KEY,
    condominio_id  UUID REFERENCES condominios(id) ON DELETE CASCADE,
    titulo         TEXT NOT NULL,
    descricao      TEXT,
    categoria      TEXT NOT NULL DEFAULT 'outros',
    prestador      TEXT,
    valor          NUMERIC(10,2),
    status         TEXT NOT NULL DEFAULT 'novo',
    data_limite    DATE,
    alerta_enviado_em TIMESTAMPTZ,
    criado_em      TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS manutencoes (
    id                BIGSERIAL PRIMARY KEY,
    condominio_id     UUID REFERENCES condominios(id) ON DELETE CASCADE,
    tipo              TEXT NOT NULL,
    descricao         TEXT,
    prestador         TEXT,
    data_realizacao   DATE,
    data_vencimento   DATE NOT NULL,
    valor             NUMERIC(10,2),
    observacoes       TEXT,
    alerta_enviado_em TIMESTAMPTZ,
    criado_em         TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE condominios DISABLE ROW LEVEL SECURITY;
ALTER TABLE demandas    DISABLE ROW LEVEL SECURITY;
ALTER TABLE manutencoes DISABLE ROW LEVEL SECURITY;

INSERT INTO condominios (nome) VALUES
    ('Vale do Paraíba'),('Palmeiras Prime 2'),('Essenza'),
    ('Pericumã'),('University Home'),('Monte Carlo'),
    ('Belvedere'),('Portal das Gaivotas'),('Marília 2'),
    ('Coronel Onofre'),('Yagua'),('Munim')
ON CONFLICT (nome) DO NOTHING;"""


def _tpl(name, request, **ctx):
    setup_ok = db.tabelas_existem()
    return templates.TemplateResponse(name, {"request": request, "setup_ok": setup_ok, **ctx})


# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/demandas")


# ─── Demandas (Kanban) ────────────────────────────────────────────────────────

@app.get("/demandas", response_class=HTMLResponse)
async def demandas_page(request: Request, cond_id: str = "", msg: str = ""):
    condominios = db.listar_condominios()
    todas = db.listar_demandas(condominio_id=cond_id or None)
    hoje = date.today().isoformat()

    # Group by status for Kanban
    colunas = {s: [] for s, *_ in db.STATUS_KANBAN}
    colunas["cancelado"] = []
    for d in todas:
        colunas.setdefault(d["status"], []).append(d)

    return _tpl("demandas.html", request,
        aba="demandas",
        condominios=condominios,
        colunas=colunas,
        status_kanban=db.STATUS_KANBAN,
        categorias=db.CATEGORIAS,
        cond_id_filtro=cond_id,
        hoje=hoje,
        msg=msg,
    )


class StatusBody(BaseModel):
    status: str


@app.post("/api/demandas/{dem_id}/status")
async def update_status_api(dem_id: int, body: StatusBody):
    db.atualizar_demanda_status(dem_id, body.status)
    return {"ok": True}


@app.post("/demandas/nova")
async def nova_demanda(
    request: Request,
    condominio_id: str = Form(...),
    titulo: str = Form(...),
    descricao: str = Form(""),
    categoria: str = Form("outros"),
    prestador: str = Form(""),
    valor: str = Form(""),
    data_limite: str = Form(""),
):
    v = float(valor.replace(",", ".")) if valor.strip() else None
    dl = data_limite if data_limite else None
    db.criar_demanda(condominio_id, titulo, descricao, categoria, prestador, v, dl)
    return RedirectResponse("/demandas?msg=Demanda+criada+com+sucesso", status_code=303)


@app.post("/demandas/{dem_id}/editar")
async def editar_demanda(
    dem_id: int,
    condominio_id: str = Form(...),
    titulo: str = Form(...),
    descricao: str = Form(""),
    categoria: str = Form("outros"),
    prestador: str = Form(""),
    valor: str = Form(""),
    data_limite: str = Form(""),
    status: str = Form("novo"),
):
    v = float(valor.replace(",", ".")) if valor.strip() else None
    dl = data_limite if data_limite else None
    db.atualizar_demanda(dem_id,
        condominio_id=condominio_id, titulo=titulo, descricao=descricao,
        categoria=categoria, prestador=prestador or None,
        valor=v, data_limite=dl, status=status,
    )
    return RedirectResponse("/demandas?msg=Demanda+atualizada", status_code=303)


@app.post("/demandas/{dem_id}/excluir")
async def excluir_demanda(dem_id: int):
    db.excluir_demanda(dem_id)
    return RedirectResponse("/demandas?msg=Demanda+removida", status_code=303)


# ─── Condomínios ──────────────────────────────────────────────────────────────

@app.get("/condominios", response_class=HTMLResponse)
async def condominios_page(request: Request, msg: str = ""):
    conds = db.listar_condominios(only_active=False)
    for c in conds:
        c["n_demandas"]    = len(db.listar_demandas(c["id"], only_open=True))
        c["n_manutencoes"] = len(db.listar_manutencoes(c["id"]))
    return _tpl("condominios.html", request, aba="condominios", condominios=conds, msg=msg)


@app.post("/condominios/novo")
async def novo_condominio(
    nome: str = Form(...),
    endereco: str = Form(""),
    responsavel: str = Form(""),
    telefone: str = Form(""),
):
    db.criar_condominio(nome, endereco, responsavel, telefone)
    return RedirectResponse("/condominios?msg=Condomínio+cadastrado", status_code=303)


@app.post("/condominios/{cond_id}/editar")
async def editar_condominio(
    cond_id: str,
    nome: str = Form(...),
    endereco: str = Form(""),
    responsavel: str = Form(""),
    telefone: str = Form(""),
):
    db.atualizar_condominio(cond_id, nome=nome, endereco=endereco,
                            responsavel=responsavel, telefone=telefone)
    return RedirectResponse("/condominios?msg=Condomínio+atualizado", status_code=303)


@app.post("/condominios/{cond_id}/desativar")
async def desativar_condominio(cond_id: str):
    db.desativar_condominio(cond_id)
    return RedirectResponse("/condominios?msg=Condomínio+desativado", status_code=303)


# ─── Manutenções ──────────────────────────────────────────────────────────────

@app.get("/manutencoes", response_class=HTMLResponse)
async def manutencoes_page(request: Request, cond_id: str = "", msg: str = ""):
    condominios = db.listar_condominios()
    manuts = db.listar_manutencoes(condominio_id=cond_id or None)
    hoje = date.today().isoformat()

    # Annotate status
    for m in manuts:
        if not m.get("data_vencimento"):
            m["_status"] = "sem_data"
            m["_diff"] = None
        else:
            diff = (date.fromisoformat(m["data_vencimento"]) - date.today()).days
            m["_diff"] = diff
            if diff < 0:
                m["_status"] = "vencido"
            elif diff <= db.DIAS_ALERTA_MANUTENCAO:
                m["_status"] = "alerta"
            else:
                m["_status"] = "ok"

    # Group by condominium
    por_cond: dict = {}
    for m in manuts:
        cid = m["condominio_id"]
        if cid not in por_cond:
            por_cond[cid] = {"cond": m.get("condominios") or {}, "items": []}
        por_cond[cid]["items"].append(m)

    # Stats
    total_vencido = sum(1 for m in manuts if m["_status"] == "vencido")
    total_alerta  = sum(1 for m in manuts if m["_status"] == "alerta")

    return _tpl("manutencoes.html", request,
        aba="manutencoes",
        condominios=condominios,
        por_cond=list(por_cond.values()),
        cond_id_filtro=cond_id,
        hoje=hoje,
        total_vencido=total_vencido,
        total_alerta=total_alerta,
        msg=msg,
    )


@app.post("/manutencoes/nova")
async def nova_manutencao(
    condominio_id: str = Form(...),
    tipo: str = Form(...),
    data_vencimento: str = Form(...),
    descricao: str = Form(""),
    prestador: str = Form(""),
    data_realizacao: str = Form(""),
    valor: str = Form(""),
    observacoes: str = Form(""),
):
    v  = float(valor.replace(",", ".")) if valor.strip() else None
    dr = data_realizacao if data_realizacao else None
    db.criar_manutencao(condominio_id, tipo, data_vencimento, descricao,
                        prestador, dr, v, observacoes)
    cid_param = f"?cond_id={condominio_id}" if condominio_id else ""
    return RedirectResponse(f"/manutencoes{cid_param}&msg=Manutenção+registrada", status_code=303)


@app.post("/manutencoes/{manut_id}/editar")
async def editar_manutencao(
    manut_id: int,
    tipo: str = Form(...),
    data_vencimento: str = Form(...),
    descricao: str = Form(""),
    prestador: str = Form(""),
    data_realizacao: str = Form(""),
    valor: str = Form(""),
    observacoes: str = Form(""),
    condominio_id: str = Form(""),
):
    v  = float(valor.replace(",", ".")) if valor.strip() else None
    dr = data_realizacao if data_realizacao else None
    db.atualizar_manutencao(manut_id,
        tipo=tipo, data_vencimento=data_vencimento, descricao=descricao or None,
        prestador=prestador or None, data_realizacao=dr,
        valor=v, observacoes=observacoes or None,
    )
    cid_param = f"?cond_id={condominio_id}" if condominio_id else ""
    return RedirectResponse(f"/manutencoes{cid_param}&msg=Manutenção+atualizada", status_code=303)


@app.post("/manutencoes/{manut_id}/excluir")
async def excluir_manutencao(manut_id: int, condominio_id: str = Form("")):
    db.excluir_manutencao(manut_id)
    cid_param = f"?cond_id={condominio_id}" if condominio_id else ""
    return RedirectResponse(f"/manutencoes{cid_param}&msg=Manutenção+removida", status_code=303)


# ─── Relatórios ───────────────────────────────────────────────────────────────

@app.get("/relatorio", response_class=HTMLResponse)
async def relatorio_page(request: Request, cond_id: str = ""):
    condominios = db.listar_condominios()
    demandas    = db.listar_demandas(condominio_id=cond_id or None)
    manutencoes = db.listar_manutencoes(condominio_id=cond_id or None)

    # Stats
    stats = {s: 0 for s, *_ in db.STATUS_KANBAN}
    for d in demandas:
        stats[d["status"]] = stats.get(d["status"], 0) + 1

    hoje = date.today().isoformat()
    return _tpl("relatorio.html", request,
        aba="relatorio",
        condominios=condominios,
        demandas=demandas,
        manutencoes=manutencoes,
        cond_id_filtro=cond_id,
        status_kanban=db.STATUS_KANBAN,
        stats=stats,
        hoje=hoje,
    )


@app.get("/relatorio/excel")
async def relatorio_excel(cond_id: str = ""):
    from relatorio_export import gerar_excel
    data = gerar_excel(cond_id or None)
    hoje = date.today().strftime("%Y-%m-%d")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="relatorio_{hoje}.xlsx"'},
    )


@app.get("/relatorio/pdf")
async def relatorio_pdf(cond_id: str = ""):
    from relatorio_export import gerar_pdf
    data = gerar_pdf(cond_id or None)
    hoje = date.today().strftime("%Y-%m-%d")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio_{hoje}.pdf"'},
    )


# ─── Setup ────────────────────────────────────────────────────────────────────

@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    setup_ok = db.tabelas_existem()
    return _tpl("setup.html", request,
        aba="setup",
        setup_ok=setup_ok,
        sql=SQL_SETUP,
    )
