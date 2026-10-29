# Gabaritos fornecidos para estudo

Gabarito preliminar é uma fonte de respostas utilizável para estudo. O rótulo não transforma sozinho uma questão em pendente quando o documento fornecido foi aceito e a resposta foi comprovada.

A configuração `config/gabaritos_estudo.json` registra os pares de caderno e gabarito aceitos pelo usuário. Cada entrada identifica a chave de catálogo e os SHA-256 dos dois PDFs. O catálogo de associações `config/gabaritos.json` continua exigindo cargo, prova e versão compatíveis.

A importação e a reparação podem certificar essas questões quando número, enunciado, alternativas, contexto, recursos e resposta constam nas regiões físicas dos PDFs. O status documental continua `preliminar`; a decisão de uso não cria uma revisão humana nem altera o documento para definitivo.

Anulações, conflitos, rejeições humanas e extração incompleta continuam impedindo a liberação. Alterar os PDFs ou remover o aceite impede o uso do certificado correspondente. Certificados de gabaritos definitivos e de documentos fornecidos não dependem desta configuração.

O aceite é calculado uma vez por par de arquivos durante preparação/importação e revalidado com as evidências reais ao registrar e consultar o certificado. A configuração separada evita alterar o hash do catálogo já registrado nos certificados anteriores.

Testes dedicados em `tests/test_gabaritos_estudo.py` verificam aceite, importação, revogação, divergências e vetos humanos.
