# Encontro 2 — Implementar: computador e WhatsApp conectados

**Objetivo:** no fim da aula, as mensagens do WhatsApp da empresa estão chegando no computador do
participante, a Central está no ar e o painel abre.

## Passos (o agente faz, o participante acompanha e faz o que é dele)
1. **Copiar o kit** para `C:\gestor-inteligente` e abrir a pasta no Claude Code.
   Dizer: "Estou no encontro 2 do curso Gestor Inteligente. Me guie."
2. **Instalar o que falta:** `scripts\conferir.ps1` mostra. Python 3.11+, Go, Node e o OpenCode
   (`npm i -g opencode-ai`), mais o Codex ou o Claude Code.
3. **Logins e chaves:** o PARTICIPANTE faz `opencode auth login` e o login no Codex ou no Claude Code.
   Criar o `.env` a partir do `.env.example` e colar a chave do Jev.
   Deixar `GI_MODO=aprovar`.
4. **Compilar e ligar a bridge:** `scripts\iniciar.ps1`. Na primeira vez aparece o QR code.
   O PARTICIPANTE escaneia: WhatsApp > Aparelhos conectados > Conectar um aparelho.
5. **Conferir que as mensagens chegam:** mandar uma mensagem de outro celular e ver
   `bridge\store\messages.db` ganhar a mensagem (o agente mostra as últimas 5).
   O histórico recente também é baixado: é ele que o Jev vai ler no encontro 3.
6. **Central e painel:** o painel abre em http://127.0.0.1:8791/ com ✅.
7. **Teste de ponta a ponta:** mandar "oi" do celular pessoal. Em ~1 minuto aparece um card em
   "Para aprovar" (ainda com o manual de EXEMPLO: é normal a resposta falar da empresa de exemplo).
   Não enviar ainda.

## Pronto quando
- [ ] Painel mostra ✅ Tudo funcionando
- [ ] Mensagem de teste apareceu no banco e virou card em "Para aprovar"
- [ ] O participante sabe ligar tudo de novo com `scripts\iniciar.ps1` e pausar no painel

## Problemas comuns
- QR expirou: fechar a janela da bridge e rodar `scripts\iniciar.ps1` de novo.
- "WhatsApp desconectado" no painel: a janela da bridge foi fechada ou o celular ficou sem internet.
