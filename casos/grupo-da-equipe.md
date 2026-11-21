# Caso: a equipe pede tarefas no grupo e a IA faz

**Problema:** a equipe avisava no grupo ("fulano vai faltar", "troca o horário de beltrano") e alguém
tinha de lançar tudo no sistema depois.

**Como fizemos:**
1. Um programa lê o grupo a cada minuto. Na primeira vez só marca o ponto de partida (não responde o histórico).
2. O **Jev** lê a mensagem e as últimas 30 do grupo: é pedido de tarefa, conversa ou algo ambíguo?
   (Corte: probabilidade ≥ 0,85 e confiança ≥ 0,65; ambíguo não faz nada.)
3. Se for tarefa: "Recebido, [nome]! Já estou lançando." → a IA faz pelas funções → confirma no grupo.
4. Mensagens da própria IA nunca viram pedido. Sem repetição automática se der erro.

**No kit:** `nucleo/grupo_equipe.py` + `empresa/equipe.md` (o que a IA pode fazer) + `empresa/equipe.json`
(nomes; a IA não vê telefones). As tarefas por pessoa aparecem no painel.
