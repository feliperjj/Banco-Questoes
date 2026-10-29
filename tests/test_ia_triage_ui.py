from PySide6.QtWidgets import QApplication

from src.ui.components.triage_review import TriageReviewDialog, _diff_html


def test_preview_escapes_markup_and_highlights_difference():
    before, after = _diff_html('<script>alert(1)</script>', 'texto novo')
    assert '<script>' not in before
    assert '&lt;' in before and '&gt;' in before
    assert '<span' in before and '<span' in after


def test_default_filter_hides_liberada_and_conferir(qt_application):
    dialog = TriageReviewDialog([1, 2, 3])
    dialog.rows = [
        {'questao_id': 1, 'status': 'liberada'},
        {'questao_id': 2, 'status': 'conferir'},
        {'questao_id': 3, 'status': 'proposta'},
    ]
    dialog._refresh_table()
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == '3'
    dialog.close()


def test_filter_options_are_available(qt_application):
    dialog = TriageReviewDialog([])
    assert [dialog.filter.itemText(i) for i in range(dialog.filter.count())] == [
        'Exceções e propostas', 'Todas', 'Propostas', 'Divergências', 'Bloqueios', 'Sem diferenças'
    ]
    dialog.close()

