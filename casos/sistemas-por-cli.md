# Caso: a IA usa os sistemas da empresa por uma ferramenta de linha de comando (CLI)

**Problema:** a empresa tinha dois sistemas na internet (um de cadastro de clientes e um de agenda).
Pedir para a IA "clicar" nas telas pelo navegador era lento, quebrava quando a tela mudava,
pedia login toda hora e, às vezes, clicava no botão errado.

**Como fizemos:** para cada sistema, pedimos a um agente (Claude Code ou Codex) que criasse uma
**ferramenta de linha de comando** — um programinha que se chama assim:

    python ferramentas/agenda.py consultar --data 2026-12-01
    python ferramentas/agenda.py marcar --data 2026-12-01 --hora 14:00 --cliente "Nome"

Ela fala direto com o sistema (pela API ou pelo mesmo endereço que a tela usa) e devolve um JSON curto:
`{"ok": true, "vagas": 2}` ou `{"ok": false, "erro": "horário lotado"}`.

**Por que é muito melhor que o navegador:**
- **Rápida:** um segundo, em vez de um minuto abrindo telas.
- **Não quebra quando a tela muda:** o desenho do site pode mudar; o endereço dos dados quase nunca muda.
- **Dá para testar sozinha,** sem WhatsApp e sem IA.
- **Segura:** a ferramenta só faz o que foi programada para fazer. A senha fica no `.env`, nunca no texto da IA.
- **Resposta exata:** a IA lê um número, não um print de tela.

**A regra mais importante (separar ler de gravar):**
1. O agente que responde o cliente **só consulta** (ler vagas, ver se a pessoa já é cliente).
2. Para **gravar** (cadastrar, marcar, cancelar), o agente devolve o pedido na resposta
   (ex.: `"marcar": {"data": ..., "hora": ...}`) e o **código** grava, confere e só então libera
   a confirmação ao cliente. Assim nada é gravado por engano no meio do raciocínio da IA.
3. "Feito" só depois do `"ok": true` do sistema.

**No kit:** `nucleo/funcoes_cli.py` já é uma ferramenta desse tipo (é por ela que a IA chama as funções).
Para ligar o sistema da SUA empresa, copie `nucleo/funcoes/_modelo.py` e peça ao seu agente:
"crie uma ferramenta de linha de comando para consultar e gravar no sistema X, com testes".
