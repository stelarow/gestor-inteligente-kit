# Lições aprendidas (casos reais, nomes trocados)

1. **Mensagem enviada duas vezes.** Um envio em lote foi "cancelado" na tela, mas continuou rodando;
   outro foi iniciado em paralelo. → Um envio por vez, com trava, e conferir o que já foi enviado
   na hora de cada mensagem.
2. **Produto errado.** O sistema "adivinhou" o produto por uma palavra-chave e escolheu o errado.
   → Quem decide é a IA lendo a conversa inteira; o código não filtra palavras.
3. **Cliente tratada como contato novo.** O sistema consultado não era a fonte da verdade, e a
   compra começava a valer numa data futura. → Definir a fonte da verdade e olhar datas futuras.
4. **Metade da conversa sumiu.** O WhatsApp guardava a mesma pessoa em dois endereços.
   → Juntar os dois endereços antes de a IA ler (o kit já faz).
5. **IA respondeu depois do humano.** A atendente já tinha resolvido pelo celular. → Se uma pessoa
   respondeu enquanto a IA pensava, a IA fica quieta (o kit já faz).
6. **"Fechado" sem pagamento.** A pessoa disse "quero" e mandou a ficha, mas não pagou.
   → Venda só com comprovante conferido ou confirmação da equipe.
7. **"Agente fora do ar" que não estava.** Era só uma resposta que demorou demais. → Mostrar o erro
   certo no painel, para o líder não desligar tudo à toa.
