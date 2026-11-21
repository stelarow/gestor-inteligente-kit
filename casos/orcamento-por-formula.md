# Caso: orçamento que demorava, feito por um agente no computador

**Problema:** cada orçamento levava tempo: abrir o arquivo ou o link que o cliente mandou, baixar,
abrir no programa certo, medir, somar material e tempo e calcular o preço. A conta mudava de pessoa para pessoa.

**Como fizemos (versão completa):**
1. Alguém manda no grupo de orçamentos (ou o cliente manda na conversa) um link ou um arquivo.
2. O **Jev** decide se é pedido de orçamento (orçar / ignorar / revisar). "Não orçar" é respeitado.
3. A IA avisa: "Já estou trabalhando no orçamento de [nome]".
4. Um agente no computador (Codex ou Claude Code) baixa o arquivo, abre **no programa de verdade**
   e lê as medidas reais (nada de "mais ou menos").
5. Fórmula da empresa, numa função: material + tempo = custo; venda = custo × o multiplicador da empresa;
   alternativa com uma reserva para imprevistos.
6. Envia uma imagem com nome, quantidade, medidas e preço; os arquivos ficam salvos numa pasta organizada.

**No kit (versão de entrada):** função `fazer_orcamento` com a fórmula em
`empresa/funcoes/orcamento.json`. A IA pede as informações que faltam e a função calcula.
**Versão completa:** tipo de tarefa `empresa/tarefas/orcamento-arquivo.md` (o agente abre a arte e mede).

**Serve para outros negócios:** gráfica (m² + acabamento), marcenaria (chapas + horas), buffet
(pessoas × cardápio), serviços (horas × valor/hora + deslocamento), oficina (peças + mão de obra).
