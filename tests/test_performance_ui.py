from threading import Event
from time import monotonic, sleep
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from src.db.database import db, init_db
from src.models import questoes_repo as repo
from src.models.eligibility_read import eligibility_read
from src.models.provenance_service import assess_version
from src.ui.database_task import DatabaseTask
from src.ui.pages.gerador_prova import GeradorProvaPage
from tests.ui_wait import wait_ui_jobs


def test_inicializacao_leve_nao_ignora_alteracao_de_schema(tmp_path, monkeypatch):
    init_db(str(tmp_path / 'schema.db'))
    queries = []
    execute = db.execute_sql
    def counted(sql, *args, **kwargs):
        queries.append(sql)
        return execute(sql, *args, **kwargs)
    monkeypatch.setattr(db, 'execute_sql', counted)
    init_db()
    assert not any(sql.lstrip().upper().startswith('CREATE') for sql in queries)
    db.execute_sql('DROP TABLE alternativas')
    init_db()
    assert 'alternativas' in db.get_tables()


def test_prefetch_preserva_decisao_e_nao_reusa_fonte_alterada(tmp_path):
    from helpers import approve_with_evidence
    init_db(str(tmp_path / 'prefetch.db'))
    approved = repo.criar_questao({'numero': 1, 'enunciado': 'Texto completo para conferência.', 'tipo': 'certo_errado', 'gabarito': 'Certo'})
    pending = repo.criar_questao({'numero': 2, 'enunciado': 'Outro texto completo.', 'tipo': 'certo_errado', 'gabarito': 'Certo'})
    source = tmp_path / 'fonte.pdf'
    approve_with_evidence(approved, source, 'Certo')
    versions = [repo.ultima_versao(q).id for q in (approved, pending)]
    expected = [assess_version(v) for v in versions]
    with eligibility_read():
        assert [assess_version(v) for v in versions] == expected
    assert repo.contar_questoes_elegiveis() == 1
    source.write_bytes(source.read_bytes() + b'alteracao')
    assert repo.contar_questoes_elegiveis() == 0


def test_ui_responde_durante_contagem_e_quantidade_nao_reconsulta(tmp_path, monkeypatch):
    init_db(str(tmp_path / 'responsive.db'))
    entered, release = Event(), Event()
    calls, ticks = [], []
    def count(filters=None):
        calls.append(dict(filters or {}))
        entered.set()
        assert release.wait(5)
        return 12
    monkeypatch.setattr(repo, 'contar_questoes_elegiveis', count)
    page = GeradorProvaPage()
    page.show()
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(monotonic()))
    timer.start(10)
    app = QApplication.instance()
    deadline = monotonic() + 3
    try:
        while not entered.is_set() and monotonic() < deadline:
            app.processEvents(); sleep(.005)
        assert entered.is_set()
        for _ in range(20):
            app.processEvents(); sleep(.005)
        assert len(ticks) >= 5
    finally:
        release.set()
        timer.stop()
    wait_ui_jobs()
    assert page.lbl_disponiveis.text().startswith('12 ')
    before = len(calls)
    page.qtd_input.setValue(20)
    app.processEvents()
    assert len(calls) == before
    assert '12 das 20' in page.lbl_disponiveis.text()


def test_resultado_antigo_nao_substitui_filtro_mais_recente(tmp_path):
    init_db(str(tmp_path / 'latest.db'))
    task = DatabaseTask()
    entered, release = Event(), Event()
    results = []
    def old():
        entered.set()
        assert release.wait(5)
        return 'antigo'
    task.submit(old, results.append, lambda error: results.append(error))
    assert entered.wait(2)
    task.submit(lambda: 'novo', results.append, lambda error: results.append(error))
    release.set()
    app = QApplication.instance()
    deadline = monotonic() + 3
    while task.running and monotonic() < deadline:
        app.processEvents(); sleep(.005)
    assert results == ['novo']


def test_original_nao_e_ampliado_e_todas_respostas_cabem(tmp_path):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage
    from src.ui.pages.execucao_prova import ExecucaoProvaPage
    image = QImage(600, 1200, QImage.Format_RGB32)
    image.fill(0xffffff)
    source = tmp_path / 'source.png'
    image.save(str(source))
    page = ExecucaoProvaPage()
    page.show()
    page.questoes = [{'id': 1, 'enunciado': 'Original extenso.', 'tipo': 'multipla_escolha',
                     'alternativas': [{'letra': a, 'texto': a} for a in 'ABCDE'],
                     'apresentacao_fonte': {'questao': [{'path': str(source)}],
                                           'contexto': [{'path': str(source)}]}}]
    page.mostrar_questao_atual()
    app = QApplication.instance()
    for width, height in ((1720, 1080), (1040, 800), (760, 640)):
        page.resize(width, height)
        for _ in range(5):
            app.processEvents()
        page._ajustar_alturas_conteudo()
        app.processEvents()
        assert page.original_view.height() >= 200
        assert page.original_view.images[0][0].pixmap().width() <= 600
        page.original_context_button.setChecked(True)
        app.processEvents()
        assert page.lbl_enunciado_titulo.text() == 'TEXTO DE APOIO'
        assert page.original_view.height() >= 200
        page.original_context_button.setChecked(False)
        app.processEvents()
        viewport = page.alternativas_scroll.viewport()
        for button in page.grupo_botoes.buttons():
            assert viewport.rect().contains(button.mapTo(viewport, QPoint(0, 0)))
            assert viewport.rect().contains(button.mapTo(viewport, button.rect().bottomRight()))
