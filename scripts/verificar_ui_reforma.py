"""Renderiza a UI com dados fictícios e banco temporário, sem tocar no acervo.

Execute: python -m scripts.verificar_ui_reforma --output caminho
Defina QT_SCALE_FACTOR antes de iniciar para verificar outra escala.
"""
import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from src.db.database import db, init_db
from src.models import questoes_repo as repo
from src.ui.main_window import MainWindow
from src.ui.pages.questoes import QuestaoDialog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setStyleSheet((Path(__file__).resolve().parents[1] / 'src/ui/styles.qss').read_text(encoding='utf-8'))
    with TemporaryDirectory() as temp:
        init_db(str(Path(temp) / 'preview.db'))
        try:
            dados = [dict(numero=i, enunciado='A administração pública deve observar os princípios previstos na Constituição Federal. Assinale a alternativa correta.',
                          tipo='multipla_escolha', gabarito='B' if i % 3 else None,
                          disciplina='Direito Constitucional', banca='Banca de exemplo', ano=2026,
                          alternativas=[dict(letra='A', texto='Legalidade e interesse exclusivamente privado.'),
                                        dict(letra='B', texto='Legalidade, impessoalidade, moralidade, publicidade e eficiência.')])
                     for i in range(1, 13)]
            repo.criar_questoes_em_lote(dados)
            window = MainWindow()
            page = window.pages.widget(2)
            page.caminho_questoes_pendente = 'concurso_analista_2026.pdf'
            page._finalizar_importacao_questoes(dados)
            for width, height in [(960, 640), (1240, 800)]:
                window.resize(width, height)
                window.show()
                window.pages.setCurrentIndex(2)
                for step in range(3):
                    page.steps.setCurrentIndex(step)
                    app.processEvents()
                    assert window.width() == width
                    button = page.btn_salvar_todas if step == 2 else page.btn_proxima
                    assert button.isVisible() and page.rect().contains(button.geometry())
                    assert window.grab().save(str(out / f'importacao-{width}-{step}.png'))
                window.pages.setCurrentIndex(1)
                app.processEvents()
                assert window.grab().save(str(out / f'acervo-{width}.png'))
            editor = QuestaoDialog(dados[0])
            editor.show()
            app.processEvents()
            assert editor.grab().save(str(out / 'editor.png'))
            editor.close()
            print(f'Layout validado: 960x640 e 1240x800; escala {window.devicePixelRatioF()}; {out}')
            page.session.carregar([], '')
            window.close()
        finally:
            db.close()


if __name__ == '__main__':
    main()
