CREATE TABLE IF NOT EXISTS questoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enunciado TEXT NOT NULL,
    tipo TEXT NOT NULL,
    disciplina TEXT,
    topico TEXT,
    banca TEXT,
    ano INTEGER,
    cargo TEXT,
    orgao TEXT,
    dificuldade TEXT,
    gabarito TEXT,
    comentario TEXT,
    ativa BOOLEAN DEFAULT 1,
    criada_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alternativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    questao_id INTEGER REFERENCES questoes(id),
    letra TEXT NOT NULL,
    texto TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    filtros TEXT,
    criada_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prova_questoes (
    prova_id INTEGER REFERENCES provas(id),
    questao_id INTEGER REFERENCES questoes(id),
    ordem INTEGER,
    PRIMARY KEY (prova_id, questao_id)
);

CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prova_id INTEGER REFERENCES provas(id),
    iniciada_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    finalizada_em DATETIME,
    total_acertos INTEGER,
    nota REAL,
    tempo_gasto_seg INTEGER
);

CREATE TABLE IF NOT EXISTS respostas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tentativa_id INTEGER REFERENCES tentativas(id),
    questao_id INTEGER REFERENCES questoes(id),
    resposta_marcada TEXT,
    correta BOOLEAN,
    tempo_resposta_seg INTEGER
);

CREATE TABLE IF NOT EXISTS revisao_espacada (
    questao_id INTEGER PRIMARY KEY REFERENCES questoes(id),
    proxima_revisao DATE,
    intervalo_dias INTEGER,
    fator_facilidade REAL DEFAULT 2.5,
    acertos_seguidos INTEGER DEFAULT 0
);