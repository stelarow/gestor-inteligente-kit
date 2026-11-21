# Encontro 3 — Implementar: o Jev (a fundo) e a curadoria inicial

**Objetivo:** o participante entende o Jev de verdade, testa com as próprias conversas e roda a
curadoria inicial, que vai mostrar com o que treinar a IA dele.

## Parte 1 — O que é o Jev
- O Jev é um modelo "System One" da TypeSafe: **não escreve texto, dá julgamentos.**
  Você manda um texto (o *estado*) e perguntas; ele devolve respostas em números.
- Por isso é **rápido, barato e fácil de usar no código**: não precisa "interpretar" uma resposta
  em texto. Exemplo real: ~1.500 conversas inteiras lidas por menos de R$ 2.
- Divisão de trabalho: o código guarda as regras e faz as contas; o Jev entende a linguagem;
  o Claude escreve as mensagens. Quem decide o que fazer com a resposta é sempre o código.

## Parte 2 — Os 3 tipos de pergunta (laboratório)
| Tipo | Quando usar | O que volta |
|---|---|---|
| `noul` (sim/não) | "A pessoa pediu para parar?" | probabilidade de SIM, de 0 a 1 |
| `choice` (escolha) | "Qual o assunto: preço, dúvida, agendamento…?" | a opção escolhida + probabilidade de cada uma + confiança |
| `score` (nota) | "Quanto interesse em comprar, de 0 a 4?" | nota com casas decimais (ex.: 3,2) + confiança |

Rodar, um de cada vez, e comentar o resultado com o grupo:
```
python nucleo\jev_laboratorio.py sim-nao
python nucleo\jev_laboratorio.py escolha
python nucleo\jev_laboratorio.py nota
python nucleo\jev_laboratorio.py juntas
```

## Parte 3 — Como escrever uma boa pergunta
- **Estado:** tudo o que o Jev precisa ler (a conversa, a data de hoje, o que a empresa vende).
  Ele só sabe o que estiver ali.
- **Instruções:** um julgamento só por pergunta, claro e completo. O nome da pergunta (ex.: `quer_noite`)
  é só para o código: o Jev não vê. Explique tudo nas instruções.
- **Critérios:** descreva cada opção/nível com situações concretas. Inclua sempre uma saída
  "nenhum/outro" quando nada servir.
- Várias perguntas sobre o mesmo texto vão **juntas no mesmo pedido** (rodam em paralelo e uma não
  vê a resposta da outra).
- Escreva em inglês ou português; nos nossos casos, instruções em inglês com o texto em português funcionaram bem.

## Parte 4 — Probabilidade, confiança e cortes
```
python nucleo\jev_laboratorio.py confianca
```
- Texto claro → probabilidade concentrada → confiança alta. Texto ambíguo ("ok") → espalhada → baixa.
- `noul` perto de 0,5 = **dúvida**, não "meio sim". Ponto de partida: SIM ≥ 0,7 e NÃO ≤ 0,3.
- **Corte conforme o risco** (três faixas): alta → o sistema age sozinho; média → pede confirmação;
  baixa → não faz nada e passa para uma pessoa.
  Exemplo real do grupo da equipe: só executa a tarefa com probabilidade ≥ 0,85 **e** confiança ≥ 0,65.
- Os cortes são um ponto de partida: teste com as suas conversas e ajuste.

## Parte 5 — Com as conversas do participante (só leitura, nada é enviado)
1. Copiar `laboratorio\minha_pergunta.json` e criar 2 perguntas do negócio do participante.
2. `python nucleo\jev_laboratorio.py minhas --pergunta laboratorio\minha_pergunta.json --quantas 10`
3. Conferir 10 respostas com o participante: acertou? Se errou, melhorar a instrução ou os critérios e rodar de novo.

## Parte 6 — Curadoria inicial (o resultado da aula)
1. Escolher a data (ex.: hoje) e testar o custo com 30 conversas:
   `python nucleo\curadoria_inicial.py --ate AAAA-MM-DD --limite 30 --sem-rascunho`
2. Rodar em todas: `python nucleo\curadoria_inicial.py --ate AAAA-MM-DD`
3. Abrir com o participante `dados\curadoria\relatorio.json`: quantas conversas, quem são, **assuntos mais
   frequentes**, quantas fecharam, quantas tiveram boa resposta, quantas precisaram de uma pessoa.
4. O rascunho do manual (`dados\curadoria\rascunho-manual.md`) é o material do encontro 4.

## Pronto quando
- [ ] O participante explica com as próprias palavras a diferença entre noul, choice e score
- [ ] Criou 1 pergunta própria e testou nas conversas dele
- [ ] Tem o relatório e o rascunho da curadoria
