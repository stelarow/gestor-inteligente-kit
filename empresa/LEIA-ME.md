# Pasta da empresa = o manual da IA

Tudo o que a IA sabe sobre a sua empresa está AQUI. Ela lê todos os arquivos `.md` desta pasta
antes de responder. Para mudar o jeito dela atender, mude estes arquivos (não o código).

O que vem pronto é uma EMPRESA DE EXEMPLO inventada ("Gráfica Rápida Exemplo").
No encontro 2, o seu agente vai ajudar você a trocar tudo pelos dados da SUA empresa.

| Arquivo | O que colocar |
|---|---|
| sobre.md | Quem é a empresa, endereço, horário, formas de pagamento |
| produtos.md | Cada produto/serviço: o que é, para quem, preço, prazo |
| produtos.json | Lista curta dos produtos (a nota dos contatos e o "chamar de volta" usam) |
| tom-de-voz.md | Como a equipe escreve (exemplos reais de mensagens boas) |
| regras.md | O que a IA nunca pode fazer e quando passar para uma pessoa |
| perguntas-frequentes.md | Perguntas que mais chegam e a melhor resposta |
| equipe.md | Só para o grupo da equipe: o que a IA pode fazer quando um colega pede |
| equipe.json | Nome de cada pessoa da equipe pelo número (a IA não vê telefones) |
| funcoes.json | Quais funções estão ligadas |
| funcoes/*.json | Configuração de cada função (fórmula do orçamento, horários da agenda...) |

Dica: a curadoria inicial (`python nucleo/curadoria_inicial.py --ate AAAA-MM-DD`) lê suas conversas
antigas e escreve um rascunho destes arquivos em `dados/curadoria/rascunho-manual.md`.
