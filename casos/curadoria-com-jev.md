# Caso: descobrir com o que treinar a IA lendo as conversas antigas

**Problema:** por onde começar o manual? O que os clientes mais perguntam? Quais respostas funcionam?

**Como fizemos:** o Jev leu todas as conversas até uma data e respondeu, em números, para cada uma:
quem é a pessoa, o assunto, se fechou, a qualidade da resposta da empresa e se precisou de uma pessoa.
Exemplo real: ~1.500 conversas lidas, ~7 milhões de tokens, **menos de R$ 2**.

**Para que serve:**
- Priorizar: os 3 assuntos mais frequentes viram as primeiras seções do manual.
- Copiar o que funciona: as conversas com nota alta viram exemplos de tom de voz.
- Evitar o que não funciona: as conversas ruins viram "erros para evitar".
- Base para a nota dos contatos e para chamar de volta quem sumiu.

**No kit:** `nucleo/curadoria_inicial.py --ate AAAA-MM-DD` → `dados/curadoria/`.
