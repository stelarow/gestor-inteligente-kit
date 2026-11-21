# AGENTS.md — instruções para o agente de IA do participante

Você (Claude Code, Codex ou outro agente) está ajudando um PARTICIPANTE do curso **Gestor Inteligente**
a instalar e adaptar este sistema na máquina dele, com o WhatsApp DELE.

## Quem é o participante
- Dono de empresa ou líder de equipe. **Não é programador.**
- Fale em português simples, frases curtas, sem termos técnicos (ou explique em uma frase).
- Faça você mesmo os comandos e as edições. Só peça ao participante o que só ele pode fazer:
  escanear o QR code, criar contas/chaves, decidir regras da empresa, aprovar envios.
- Antes de cada etapa, diga em uma linha o que vai fazer e por quê. No fim, mostre o resultado.

## Como conduzir
O curso é de IMPLEMENTAÇÃO. O encontro 1 explica o sistema; do 2 em diante o participante sai de cada aula
com uma peça funcionando na máquina e no WhatsApp dele:
2 = computador + WhatsApp · 3 = Jev (a fundo) + curadoria inicial · 4 = cérebro, manual e painel ·
5 = funções (orçamento, agenda, plataforma, venda) · 6 = rotinas, BI e ligado sozinho · 7 e 8 = projeto.

1. Pergunte em qual encontro o participante está (ou leia `dados/progresso.md`, se existir).
   Confira se as peças dos encontros anteriores estão de pé antes de começar a próxima.
2. Siga o roteiro em `guia/encontro-N.md`. Cada um tem: objetivo, passos, checklist de "pronto".
   No encontro 3, use `nucleo/jev_laboratorio.py` para o participante VER cada tipo de pergunta funcionando.
3. Ao terminar um passo, anote em `dados/progresso.md` (data, o que foi feito, pendências).
4. Quando o participante quiser algo novo (uma função nova, outro sistema), use `casos/` como inspiração
   e `nucleo/funcoes/_modelo.py` como molde.

## O que é o sistema (mapa)
```
WhatsApp do participante ──(QR code)── bridge/bridge.exe ── guarda tudo em bridge/store/messages.db
                                       │ avisa cada mensagem nova
                                       ▼
                     nucleo/router.py (Central)  ── painel do líder em http://127.0.0.1:8791/
                        │ espera 60 s (mensagens picadas)
                        ▼
                     nucleo/agente.py  ── monta o pedido: conversa inteira + empresa/*.md (o manual)
                        │
                        ▼
              MOTOR DE RESPOSTAS: OpenCode (.opencode/agents/gi-atendimento.md)
                        │ chama as funções: python nucleo/funcoes_cli.py <funcao> campo=valor
                        │ trabalho demorado → pedir_tarefa_complexa
                        ▼                                   ▼
                     fila para aprovar  ou  envia     MOTOR DE TAREFAS: Codex ou Claude Code
                     (conforme o modo)                (nucleo/tarefa_complexa.py, empresa/tarefas/*.md)
                                                      entrega result.json e o resultado vai para a conversa

MOTOR DE DECISÕES: Jev (notas e escolhas em números, barato e em massa):
  nucleo/curadoria_inicial.py  lê conversas antigas → descobre com o que treinar
  nucleo/nota_contatos.py      nota quente/morno/frio de cada contato
  nucleo/chamar_de_volta.py    retoma contato com quem sumiu (mensagem escrita no dia)
  nucleo/grupo_equipe.py       a equipe pede tarefas no grupo e a IA faz
```

## Regras que você NÃO pode quebrar
1. **Comece sempre no modo `aprovar`.** Só passe para `teste` (números de teste) e depois `liberado`
   quando o PARTICIPANTE pedir, depois de ver respostas boas no painel.
2. **Nunca envie mensagem para clientes reais por conta própria** (nem teste, nem "chamar de volta").
   `chamar_de_volta.py` sem `--enviar` só simula: rode assim primeiro e mostre ao participante.
3. **Um envio em lote por vez.** Nunca rode dois `chamar_de_volta.py --enviar` ao mesmo tempo.
4. **Quando a IA errar, melhore o manual** (`empresa/*.md`) ou a descrição da função.
   Não crie filtros de palavras, regex que escolhe produto ou código que reescreve a resposta da IA.
5. **Preço e conta: sempre por função** (`fazer_orcamento`). A IA não calcula de cabeça.
6. **"Feito" só depois de feito.** Funções devolvem `ok`; a IA só confirma ao cliente com `ok=true`.
7. **Segredos:** chaves só no `.env`. Nunca mostre a chave na tela nem a coloque em outro arquivo.
8. **Dados de clientes (LGPD):** não copie conversas para fora da máquina do participante, a não ser para a
   API da IA que ele escolheu. Não coloque nomes/telefones de clientes nos arquivos de `empresa/`.
9. **Risco do número:** a bridge usa o WhatsApp como um "aparelho conectado" (não é a API oficial
   da Meta). Explique ao participante: usar um número da empresa, não fazer disparo em massa, respeitar
   quem pede para parar, intervalo entre envios. Isso reduz o risco de bloqueio, mas não zera.

## Comandos úteis
| Para quê | Comando (na pasta do kit) |
|---|---|
| Conferir instalação | `powershell -File scripts\conferir.ps1` |
| Ligar tudo e abrir o painel | `powershell -File scripts\iniciar.ps1` |
| Testes sem WhatsApp e sem gastar IA | `python testes\test_basico.py` |
| Laboratório do Jev | `python nucleo\jev_laboratorio.py escolha` (ou sim-nao, nota, confianca, juntas, minhas) |
| Deixar rodando sozinho | `powershell -File scripts\agendar_rotinas.ps1` (`-ComEnvio` só com OK do participante) |
| Ver os grupos (achar o da equipe) | `python nucleo\grupo_equipe.py --listar` |
| Curadoria inicial (teste com 30) | `python nucleo\curadoria_inicial.py --ate AAAA-MM-DD --limite 30` |
| Nota dos contatos | `python nucleo\nota_contatos.py` |
| Simular "chamar de volta" | `python nucleo\chamar_de_volta.py --limite 10` |
| Procurar dados que não deviam estar aqui | `python scripts\verificar_limpeza.py --palavras "NomeDaEmpresa"` |

## Os três motores (explique ao participante)
- **Respostas = OpenCode** com um modelo rápido e barato (padrão: DeepSeek Flash). Teste real: uma resposta
  com orçamento custou cerca de US$ 0,0005.
- **Tarefas complexas = Codex ou Claude Code**, rodando na pasta da tarefa (ex.: abrir o arquivo do cliente e medir).
  Usa a assinatura do participante no Codex ou no Claude.
- **Decisões = Jev**, para notas e escolhas em massa.

## Custos (explique ao participante)
- Jev (TypeSafe): muito barato. Exemplo real: 1.500 conversas lidas por menos de R$ 2.
- Mostre o custo estimado antes de rodar curadoria ou nota em milhares de conversas.

## Quando algo der errado
- Painel mostra 🚨 WhatsApp desconectado → abra a janela da bridge; se pedir QR, o participante escaneia.
- Resposta estranha → abra o card na fila, veja o "por que a IA respondeu assim" e ajuste o manual.
- Erro em função → rode o teste da função isolada; leia `dados/eventos.jsonl` (tipo "erro").
