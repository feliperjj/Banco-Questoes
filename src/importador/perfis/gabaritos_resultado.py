"""Acumulação de gabaritos sem sobrescrever respostas conflitantes."""
class MapaGabarito(dict):
    def __init__(self):
        super().__init__()
        self.conflitos = set()
        self.avisos = []

    def incorporar(self, respostas):
        self.conflitos.update(getattr(respostas, "conflitos", ()))
        for n in self.conflitos:
            self.pop(n, None)
        for n, resposta in respostas.items():
            if n in self.conflitos:
                continue
            if n in self and self[n] != resposta:
                equivalentes = {'X':'Anulada','ANULADA':'Anulada','CERTO':'Certo','ERRADO':'Errado'}
                if equivalentes.get(str(self[n]).upper(),self[n]) != equivalentes.get(str(resposta).upper(),resposta):
                    self.pop(n)
                    self.conflitos.add(n)
                    continue
            self[n] = resposta
        if self.conflitos:
            self.avisos = ['Respostas conflitantes na fonte; confira os números: '+', '.join(map(str,sorted(self.conflitos)))]
