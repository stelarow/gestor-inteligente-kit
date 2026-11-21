# Caso: chamar de volta quem sumiu

**Problema:** centenas de conversas antigas com gente interessada que nunca fechou.

**Como fizemos:** nota de cada contato pelo Jev → fila só com quem quer o que a empresa oferece
(produto, horário, modalidade) → mensagem personalizada escrita pela IA **no dia do envio** → até
50 por dia, de segunda a sábado, às 10h, com intervalo entre os envios. Resultados no painel.

**Regras que viraram lei:**
- Nunca preparar mensagens dias antes. A conversa muda (a pessoa pode ter marcado visita ontem).
- Não chamar quem quer algo que a empresa não tem (ex.: um horário que não existe).
- Revalidar na hora do envio. Um processo de envio por vez.
- Quem pediu para parar não recebe mais nada.

**No kit:** `nucleo/nota_contatos.py` + `nucleo/chamar_de_volta.py` (simula por padrão).
