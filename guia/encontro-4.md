# Encontro 4 — Implementar: o cérebro, o manual da empresa e o painel

**Objetivo:** a IA responde como a empresa do participante, e o líder controla tudo pelo painel.

## Passos
1. **Trocar o exemplo pela empresa do participante** na pasta `empresa/`, usando o rascunho da curadoria:
   `sobre.md`, `produtos.md`, `produtos.json` (com `"tem": false` no que NÃO faz), `tom-de-voz.md`,
   `regras.md`, `perguntas-frequentes.md`. Onde o rascunho tiver [CONFIRMAR], o participante decide.
2. **Testar com as 10 perguntas da tarefa de casa**, mandando do celular pessoal. Para cada resposta no
   painel: ler o "por que a IA respondeu assim"; se errou, **corrigir o manual** (não o código).
3. **Treinar pelo painel:** editar e enviar; 👍/👎 com comentário (a IA lê os últimos comentários).
4. **Passar para uma pessoa:** configurar `GI_NUMERO_LIDER`, simular uma reclamação e ver o aviso chegar.
   Devolver a conversa para a IA na aba "Com uma pessoa".
5. **Fotos e áudios:** mandar uma foto e um áudio. Áudio precisa de `pip install faster-whisper` (opcional).
6. **Subir um degrau:** pôr os números da equipe em `GI_NUMEROS_TESTE` e mudar para 🧪 no painel.
   A equipe faz papel de cliente por 15 minutos.

## Pronto quando
- [ ] Nenhum texto da empresa de exemplo sobrou em `empresa/`
- [ ] As 10 perguntas têm respostas aprovadas sem edição
- [ ] Aviso de "conversa para uma pessoa assumir" chegou no celular do líder
