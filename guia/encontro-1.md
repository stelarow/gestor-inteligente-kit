# Encontro 1 — Entendendo o sistema (a única aula de explicação)

**Objetivo:** o participante entende as peças, vê o sistema funcionando de verdade e sai com tudo
preparado para começar a implementar no encontro 2.

## Roteiro da aula
1. **Demonstração ao vivo** (instrutor): uma mensagem chega, a IA responde, o líder aprova no painel;
   um pedido no grupo da equipe vira tarefa feita; a aba de contatos quentes.
2. **O mapa das peças** (é o que vamos montar, uma por aula):
   | Peça | O que faz | Aula em que o participante monta |
   |---|---|---|
   | Computador + WhatsApp | O WhatsApp da empresa conectado ao computador (bridge) | 2 |
   | Jev | Lê conversas e dá notas e escolhas em números, rápido e barato | 3 |
   | Cérebro (OpenCode) + manual | Lê a conversa e o manual da empresa e escreve a resposta | 4 |
   | Tarefas complexas (Codex ou Claude Code) | Trabalho demorado no computador, como abrir e medir o arquivo de um orçamento | 5 |
   | Painel do líder | Aprovar, corrigir, treinar, ver os números | 4 |
   | Funções | Orçamento, agenda, cadastro na plataforma, venda | 5 |
   | Rotinas | Nota dos contatos, chamar de volta, grupo da equipe, ligado sozinho | 6 |
3. **Três motores, cada um no que faz melhor:**
   - **OpenCode** (modelo rápido e barato) escreve as respostas e chama as funções. Frações de centavo por resposta.
   - **Codex ou Claude Code** fazem as tarefas complexas e demoradas no computador (ex.: orçamento a partir de um arquivo enviado).
   - **Jev** decide em números (sim/não, qual opção, que nota), em massa e por centavos.
4. **Regras de segurança** que valem o curso todo: começar aprovando tudo, sem disparo em massa,
   chaves só no `.env`, dados dos clientes ficam na máquina do participante.
5. **Cada participante escolhe o caso** que quer ter pronto no fim (atendimento, orçamento, cadastro,
   equipe ou retomar contatos).

## Material de apoio
- `guia/como-funciona-um-atendimento.md`: as 7 etapas de um atendimento, com o lugar de cada peça no kit.
- Instalar o Claude Code no Windows (PowerShell, sem administrador):
  `irm https://claude.ai/install.ps1 | iex` → feche e abra outra janela → `claude --version` →
  na pasta do projeto, `claude` (entra com a conta paga, plano Pro ou maior) → `claude doctor` confere tudo.
  Git para Windows é recomendado (não obrigatório). Fonte: code.claude.com/docs/en/setup.
- Jeito padrão de abrir o Claude Code no curso (dentro da pasta de trabalho):
  `claude --dangerously-skip-permissions --chrome --remote-control`
  - `--dangerously-skip-permissions`: não pede licença a cada passo (edita, roda comandos, instala até terminar).
    Use numa pasta só de trabalho, longe de arquivos pessoais, com cópia do kit para voltar atrás.
  - `--remote-control`: a sessão aparece no app do Claude no celular (aba Code) ou pelo QR code do terminal.
    Tudo roda no computador: deixe-o ligado e o terminal aberto.
  - `--chrome`: liga a extensão oficial Claude no Chrome; ele usa o Chrome de vocês, com os logins, e para em login/captcha.
  Fontes: `claude --help` e code.claude.com/docs (permission-modes, remote-control, chrome).

## Tarefa de casa (obrigatória para o encontro 2)
- [ ] Computador com Windows 10/11 que fique ligado no horário de atendimento
- [ ] Número de WhatsApp da EMPRESA (não o pessoal) com o celular em mãos
- [ ] Conta no OpenCode com crédito (motor de respostas)
- [ ] Assinatura do Codex (ChatGPT) ou do Claude (motor de tarefas e agente que guia a instalação)
- [ ] Conta na TypeSafe (typesafe.ai), para a chave do Jev
- [ ] Anotar 10 perguntas que os clientes mais fazem
