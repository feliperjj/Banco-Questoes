"""Regressões de ausência física, divergência, cache e aplicação assistida."""
from io import BytesIO
import json
from threading import Event

import pytest
from PIL import Image

from src.importador import ia_revisao as review


def _image():
    out = BytesIO()
    Image.new('RGB', (160, 32), 'white').save(out, format='PNG')
    return out.getvalue()


def _evidence(**changes):
    value = {'letter': 'E', 'pdf': '(E) texto correto', 'ocr': '(E) texto correto',
             'located': True, 'image_bytes': _image(), 'source_sha256': 'a' * 64,
             'page': 1, 'bounds': [0, 10, 100, 30], 'reason': 'marcador_pdf'}
    value.update(changes)
    return value


class FakeRuntime:
    fingerprint = 'modelo-e-config-1'
    def __init__(self, text='(E) texto correto'):
        self.calls = 0
        self.text = text
    def transcribe(self, image, cancel_event=None):
        self.calls += 1
        return {'encontrado': True, 'texto': self.text}
    def close(self):
        pass


def test_ausencia_de_marcador_bloqueia_ia_mesmo_se_modelo_inventaria(tmp_path):
    runtime = FakeRuntime('(E) inventado')
    result = review.analyze_evidence(_evidence(located=False), 'atual', runtime=runtime,
                                    cache_dir=tmp_path, force_model=True)
    assert result['status'] == 'abster' and result['proposal'] is None
    assert runtime.calls == 0 and not result['model_called']


def test_concordancia_pdf_ocr_evitar_modelo_e_nao_aprova(tmp_path):
    runtime = FakeRuntime()
    result = review.analyze_evidence(_evidence(), 'texto errado', runtime=runtime, cache_dir=tmp_path)
    assert result['proposal'] == 'texto correto'
    assert result['requires_review'] and result['automatic_approval'] is False
    assert runtime.calls == 0


def test_ia_sem_rotulo_ou_sem_apoio_nao_vira_proposta(tmp_path):
    for text in ('texto correto', '(E) texto inventado', '(D) texto correto'):
        result = review.analyze_evidence(_evidence(), 'texto errado', runtime=FakeRuntime(text),
            cache_dir=tmp_path / str(len(text)), force_model=True)
        assert result['status'] == 'divergencia' and result['proposal'] is None


def test_cache_reutiliza_leitura_mas_recompara_valor_atual_e_invalida_modelo(tmp_path):
    runtime = FakeRuntime()
    first = review.analyze_evidence(_evidence(), 'errado', runtime=runtime, cache_dir=tmp_path, force_model=True)
    second = review.analyze_evidence(_evidence(), 'texto correto', runtime=runtime, cache_dir=tmp_path, force_model=True)
    assert first['status'] == 'proposta' and second['status'] == 'manter'
    assert runtime.calls == 1 and second['cache_hit']
    runtime.fingerprint = 'modelo-2'
    review.analyze_evidence(_evidence(), 'errado', runtime=runtime, cache_dir=tmp_path, force_model=True)
    assert runtime.calls == 2
    changed = _evidence(source_sha256='b' * 64)
    review.analyze_evidence(changed, 'errado', runtime=runtime, cache_dir=tmp_path, force_model=True)
    assert runtime.calls == 3


def test_cache_malformado_nao_vira_aprovacao(tmp_path):
    runtime = FakeRuntime()
    review.analyze_evidence(_evidence(), 'errado', runtime=runtime, cache_dir=tmp_path, force_model=True)
    cache = next(tmp_path.glob('*.json'))
    data = json.loads(cache.read_text(encoding='utf-8'))
    data['transcript'] = {'encontrado': 'true', 'texto': '(E) texto correto'}
    cache.write_text(json.dumps(data), encoding='utf-8')
    review.analyze_evidence(_evidence(), 'errado', runtime=runtime, cache_dir=tmp_path, force_model=True)
    assert runtime.calls == 2


def test_cancelamento_e_saida_invalida_nao_gravam_cache(tmp_path):
    event = Event(); event.set()
    with pytest.raises(InterruptedError):
        review.analyze_evidence(_evidence(), 'texto', cancel_event=event, cache_dir=tmp_path)
    runtime = FakeRuntime()
    runtime.transcribe = lambda *a, **k: {'encontrado': False, 'texto': 'null'}
    with pytest.raises(ValueError, match='inválida'):
        review.analyze_evidence(_evidence(), 'texto', runtime=runtime, cache_dir=tmp_path, force_model=True)
    assert not list(tmp_path.glob('*.json'))


def test_rotulos_repetidos_nao_escolhem_questao_por_posicao():
    class Page:
        width = 500
        def crop(self, bounds): return self
        def extract_words(self, **kwargs):
            return [{'text': '(E)', 'x0': 10, 'x1': 20, 'top': top, 'bottom': top + 10} for top in (20, 100)]
    assert review._native_target(Page(), (0, 0, 500, 400), 'E') == (None, 'marcador_repetido')


def test_linha_anterior_nao_entra_no_recorte_da_alternativa():
    class Page:
        width = 500
        def crop(self, bounds): return self
        def extract_words(self, **kwargs):
            return [dict(text='(D)', x0=10, x1=20, top=20, bottom=30),
                    dict(text='(E)', x0=10, x1=20, top=31, bottom=41),
                    dict(text='texto', x0=24, x1=80, top=31, bottom=41)]
    bounds, reason = review._native_target(Page(), (0, 0, 100, 50), 'E')
    assert bounds[1] > 30 and bounds[3] >= 41 and reason == 'marcador_pdf'


def test_espaco_entre_paragrafos_nao_transforma_prefixo_em_alternativa_completa():
    class Page:
        width = 500
        def crop(self, bounds): return self
        def extract_words(self, **kwargs):
            return [dict(text='(E)', x0=10, x1=20, top=20, bottom=30),
                    dict(text='Primeiro', x0=24, x1=80, top=20, bottom=30),
                    dict(text='continua', x0=24, x1=80, top=55, bottom=65)]
    assert review._native_target(Page(), (0, 0, 100, 90), 'E') == (None, 'limite_ambiguo')


def test_recorte_que_interrompe_palavra_ou_continuacao_e_bloqueado():
    class Page:
        width = 500
        def crop(self, bounds): return self
        def extract_words(self, **kwargs):
            return [dict(text='(E)', x0=10, x1=20, top=20, bottom=30),
                    dict(text='continua', x0=24, x1=80, top=31, bottom=41)]
    assert review._native_target(Page(), (0, 0, 100, 38), 'E') == (None, 'trecho_cortado')


def test_lista_interna_recuada_nao_e_fim_da_alternativa():
    class Page:
        width = 500
        def crop(self, bounds): return self
        def extract_words(self, **kwargs):
            return [dict(text='(E)', x0=10, x1=20, top=20, bottom=30),
                    dict(text='Lista:', x0=24, x1=80, top=20, bottom=30),
                    dict(text='(A)', x0=30, x1=40, top=32, bottom=42),
                    dict(text='interna', x0=45, x1=90, top=32, bottom=42),
                    dict(text='continua', x0=24, x1=90, top=44, bottom=54)]
    bounds, _ = review._native_target(Page(), (0, 0, 100, 70), 'E')
    assert bounds[3] >= 54


def test_ocr_nao_corta_alternativa_multilinha_na_primeira_deteccao():
    lines = [dict(text='A) Primeira linha', confidence=.95, bbox=[10, 20, 200, 35]),
             dict(text='continuação inteira', confidence=.95, bbox=[30, 38, 250, 53]),
             dict(text='B) Outra opção', confidence=.95, bbox=[10, 60, 220, 75])]
    bounds = review._ocr_target(lines, 'A', (0, 0, 300, 100), 1)
    assert bounds[3] > 53 and bounds[3] < 60
