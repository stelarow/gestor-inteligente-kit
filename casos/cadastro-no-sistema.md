# Caso: cadastro automático no sistema da empresa depois do pagamento

**Problema:** depois que o cliente pagava, alguém precisava cadastrar o cliente no sistema da empresa,
liberar o acesso e avisar a equipe. Havia esquecimentos e atrasos.

**Como fizemos:**
1. A IA pede os dados (nome, documento, contato) e o comprovante.
2. Confere o comprovante pela imagem (valor e nome). Só "quero" ou ficha preenchida **não** é venda.
3. Pede em silêncio o SIM do responsável (mensagem só para ele; o cliente não vê).
4. Com o SIM, cadastra no sistema da empresa por uma ferramenta própria (veja `casos/sistemas-por-cli.md`).
5. Avisa o cliente (boas-vindas) e a equipe (no grupo).

**O que aprendemos:**
- Defina **qual sistema é a fonte da verdade** de quem já é cliente. Consultar o sistema errado
  fez a IA tratar uma cliente que já tinha comprado como contato novo.
- Considere datas futuras: o serviço pode começar na semana que vem e ainda não aparecer na lista de hoje.
- A função só devolve "ok" quando o sistema confirmou. A IA só fala "cadastrado" depois disso.

**No kit:** `cadastrar_cliente` (planilha local ou `url_api`) + `registrar_venda`.
