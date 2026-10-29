from src.models.ia_metrics import record_session, summarize_sessions


def test_medicao_nao_inventa_economia_nem_label_de_treino(tmp_path):
    record_session(field='alternativas', assisted=False, outcome='salvou', elapsed_seconds=30, directory=tmp_path)
    record_session(field='alternativas', assisted=True, outcome='salvou', elapsed_seconds=20, waiting_seconds=5, directory=tmp_path)
    record_session(field='alternativas', assisted=True, outcome='cancelou', elapsed_seconds=2, directory=tmp_path)
    result = summarize_sessions(tmp_path)
    assert result['manual'] == {'sessions': 1, 'mean_seconds': 30}
    assert result['assistido'] == {'sessions': 1, 'mean_seconds': 20}
    assert result['time_saved_verified'] is False
