# Encontro 6 — Implementar: rotinas, BI do time e o sistema ligado sozinho

**Objetivo:** o sistema trabalha sozinho todo dia, e o líder acompanha o time pelos números.

## Passos
1. **Nota dos contatos (Jev):** `python nucleo\nota_contatos.py` → aba 🔥 Contatos.
   Ver com o participante: quantos quentes, o que mais trava a compra, para qual produto.
2. **Chamar de volta:** `python nucleo\chamar_de_volta.py --limite 10` (SIMULA). Ler as 10 mensagens
   com o participante. Só com o OK dele: `--enviar --limite 5` e acompanhar as respostas no painel.
3. **Grupo da equipe:** `python nucleo\grupo_equipe.py --listar` → JID em `GI_GRUPO_EQUIPE`;
   preencher `empresa/equipe.md` e `empresa/equipe.json`. Ligar com `python nucleo\grupo_equipe.py`
   e testar 3 pedidos no grupo ("marca…", "faz o orçamento…", "fechou a venda…").
4. **BI do time:** abrir o painel em 7 e 30 dias. Ler juntos: conversas, respostas, passadas para uma
   pessoa, orçamentos, agendamentos, vendas por pessoa, assuntos.
5. **Ligado sozinho:** `powershell -File scripts\agendar_rotinas.ps1` (Central e WhatsApp religam se
   caírem, grupo sempre ligado, nota às 8h). Só depois de aprovar as mensagens: `-ComEnvio`.
6. **Decidir o nível:** continuar em ✍️ aprovar ou passar para 🚀 no horário comercial.

## Pronto quando
- [ ] Rotinas aparecem no Agendador de Tarefas e voltam sozinhas depois de reiniciar o PC
- [ ] Um colega pediu uma tarefa no grupo e a IA fez
- [ ] O participante lê o painel e diz o que vai melhorar na semana
