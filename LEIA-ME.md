# 🧠 Gestor Inteligente — kit do participante

*A IA trabalha como braço direito do líder.*

Um atendente com IA no seu WhatsApp que **responde clientes**, **faz tarefas** (orçamento, agenda,
cadastro), **ajuda a equipe no grupo** e mostra tudo num **painel para o líder**.

## Como começar
1. Abra esta pasta no Claude Code (ou no seu agente de IA).
2. Diga: **"Estou no encontro 2 do curso Gestor Inteligente. Me guie."** (o encontro 1 é a explicação, na aula)
3. O agente lê o `AGENTS.md` e faz a instalação com você, passo a passo.

## O que tem aqui
| Pasta | O que é |
|---|---|
| `empresa/` | O manual da sua empresa (é o que a IA sabe). Vem com uma empresa de EXEMPLO. |
| `nucleo/` | O sistema: Central, IA, funções, painel, rotinas com o Jev. |
| `bridge/` | A conexão com o WhatsApp (QR code). |
| `guia/` | O roteiro de cada um dos 8 encontros (do 2 em diante, você implementa) e `como-funciona-um-atendimento.md`. |
| `laboratorio/` | Suas perguntas para testar o Jev (encontro 3). |
| `casos/` | Casos reais que inspiram: atendimento, orçamento, cadastro, sistemas por linha de comando, grupo da equipe... |
| `scripts/` | Ligar, conferir e verificar se não há dados pessoais antes de compartilhar. |
| `testes/` | Testes que rodam sem WhatsApp e sem gastar IA. |

## Segurança em 3 regras
1. Começa em **"Eu aprovo antes"**: nada sai sem você ver.
2. Suas chaves ficam só no arquivo `.env`.
3. Sem disparo em massa: a conexão não é a API oficial do WhatsApp.

## Créditos
A conexão com o WhatsApp usa a biblioteca aberta whatsmeow (licença MPL-2.0).
