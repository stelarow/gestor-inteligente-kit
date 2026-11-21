# Encontro 5 — Implementar: funções (orçamento, agenda, plataforma, venda)

**Objetivo:** a IA passa a FAZER coisas no negócio do participante, não só responder.

## Passos
1. **Orçamento:** escrever a fórmula do participante em `empresa/funcoes/orcamento.json`
   (variáveis com preço por unidade, custo fixo, multiplicador, mínimo, prazo).
   Caso de referência: `casos/orcamento-por-formula.md` (arquivo do cliente → preço).
   Testar 3 pedidos e conferir na calculadora.
2. **Agenda:** horários e vagas em `empresa/funcoes/agenda.json`. Testar marcar, lotar e cancelar.
   Configurar `GI_GRUPO_EQUIPE` para a equipe ser avisada.
3. **Cadastro no sistema da empresa do participante:** começar gravando na planilha (`dados/cadastros.csv`).
   Depois o agente adapta `nucleo/funcoes/cadastro.py` ao sistema do participante (API, planilha Google, n8n).
   Caso de referência: `casos/cadastro-no-sistema.md`.
4. **Venda:** testar o fluxo completo pelo número de teste: dados → foto do comprovante → cadastro →
   venda registrada (💰 no painel).
5. **Uma função só do participante:** copiar `nucleo/funcoes/_modelo.py`, criar (ex.: status do pedido,
   frete, estoque, 2ª via) e ligar em `empresa/funcoes.json`.

## Tarefa complexa (Codex ou Claude Code)
6. Ver o tipo de tarefa de exemplo `empresa/tarefas/orcamento-arquivo.md` e escrever um do negócio do participante.
7. Testar sem WhatsApp: `python nucleo\tarefa_complexa.py --testar orcamento-arquivo "arte.pdf, banner 60 x 90"`.
   Abrir a pasta da tarefa em `dados\tarefas\` e ver o que o motor fez.
8. Testar pelo WhatsApp: o cliente manda o link, a IA avisa "já estou trabalhando" e o resultado chega sozinho.

## Pronto quando
- [ ] Orçamento certo, horário marcado, cadastro feito e venda no painel
- [ ] A função própria do participante funcionando
