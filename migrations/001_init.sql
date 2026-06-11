-- Síndico App — Schema inicial

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

-- Desabilitar RLS (sistema single-user)
ALTER TABLE condominios DISABLE ROW LEVEL SECURITY;
ALTER TABLE demandas    DISABLE ROW LEVEL SECURITY;
ALTER TABLE manutencoes DISABLE ROW LEVEL SECURITY;

-- Pré-popular condomínios
INSERT INTO condominios (nome) VALUES
    ('Vale do Paraíba'),
    ('Palmeiras Prime 2'),
    ('Essenza'),
    ('Pericumã'),
    ('University Home'),
    ('Monte Carlo'),
    ('Belvedere'),
    ('Portal das Gaivotas'),
    ('Marília 2'),
    ('Coronel Onofre'),
    ('Yagua'),
    ('Munim')
ON CONFLICT (nome) DO NOTHING;
