# Instruções dos agentes — aora-controls

Repositório **público**. Leia `README.md` e `docs/adr/0001-controls-outside-the-hub.md` antes de mudar qualquer coisa.

## Invariantes

1. **Nada sensível.** Não comite texto de normas ou conhecimento do Hub (só `aora.id` e hash), dados ou código de
   projetos da organização, credenciais, nomes de máquinas, IPs, caminhos de usuário, logs reais. Exemplos de teste são
   sintéticos e mínimos. Em dúvida, não comite e pergunte.
2. Todo controle referencia exatamente uma norma (`norm: <aora.id>`) e declara o `norm_hash` contra o qual foi validado.
   O controle não reinterpreta a norma: implementa o critério verificável dela. Dúvida sobre o critério → issue no Hub,
   não ajuste silencioso aqui.
3. A ferramenta é escolha do controle, nunca da norma. Trocar de ferramenta é um controle novo ou uma versão nova do
   descritor, com registro; nunca edição silenciosa.
4. Contrato de saída fixo: JSON com `norm`, `control`, `norm_hash`, `violations[]`; saída 0 = sem violação, 1 = com
   violação, 2 = erro do controle. Mensagens de violação citam arquivo e linha, não copiam blocos de código do projeto.
5. Todo controle tem `tests/pass/` e `tests/fail/` que o CI executa. Controle sem os dois casos é `experimental`.
6. O runner nunca altera o projeto que verifica; só lê e escreve `.aora/baseline.json` quando chamado para isso, e um
   baseline só diminui.
7. Sem dependências além da biblioteca padrão do Python no runner. Um controle pode depender de ferramenta externa
   (import-linter, dependency-cruiser…) desde que declare e que os testes pulem com mensagem clara quando ela faltar.
8. Não há autorização aqui: passar num controle não é aprovação de merge, deploy ou exceção.

## Entrega

Mudança pequena e testável; PR descreve a norma afetada, o que o controle detecta e o que **não** detecta, evidência
dos testes, e rollback. Sem push/merge sem autoridade externa.
