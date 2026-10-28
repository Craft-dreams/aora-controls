# ADR-0001 — Controles fora do Hub: registro de decisão, contrato do controle e runner

- **Status:** Proposed
- **Data:** 2026-10-28
- **Contexto de origem:** Knowledge Hub ADR-0002 (rev. 2) fixa que o Hub guarda só conhecimento e normas, e que o
  controle que aplica uma norma é outra decisão, tomada e mantida fora do Hub. Esta ADR decide o "fora".
- **Decisão do operador (2026-10-28):** repositório público; nada sensível entra aqui.

## 1. Contexto

Uma norma do Hub tem enunciado e critério verificável. Para que valha no código, alguém constrói um controle (regra de
linter, teste de arquitetura, verificador AST, regra de ArchUnit/Checkstyle/Semgrep, ou um agente revisor com checklist)
e um projeto decide adotá-lo em algum modo. Essas escolhas precisam de um lugar, um formato de registro e um contrato de
execução comuns, senão cada projeto reinventa e a rastreabilidade norma → regra se perde.

## 2. Decisão

### 2.1 Onde vive cada coisa

| Artefato | Onde | Visibilidade |
|---|---|---|
| Norma e conhecimento | Knowledge Hub | privado |
| Controle reutilizável (genérico, parametrizável) | este repositório, `controls/<NORM-ID>/<control-id>/` | público |
| Controle específico de um projeto | o próprio projeto (ex.: `tests/architecture/`) | a do projeto |
| Registro de decisão norma → controle → modo | o projeto, `.aora/norms.yaml` | a do projeto |
| Baseline da catraca e exceções | o projeto, `.aora/baseline.json`, `.aora/exceptions.yaml` | a do projeto |
| Runner que executa tudo | este repositório, `src/aora_controls/` | público |

Este repositório **não** contém texto de norma: só `aora.id`, `norm_hash` e o critério reescrito em termos de
implementação dentro do README do controle.

### 2.2 Descritor do controle — `control.yaml`

```yaml
id: ARCH-LAYERS-001-py-ast          # único neste repositório
norm: ARCH-LAYERS-001                # aora.id no Hub
norm_hash: "<sha256 do texto da norma no momento da validação>"
status: active                       # experimental | active | retired
kind: deterministic                  # deterministic | judgment
languages: [python]
tool: python-ast                     # aqui a ferramenta aparece
params:
  domain: {default: app/domain, description: pacote da camada de domínio}
  infra:  {default: app/infrastructure, description: pacote da camada de infraestrutura}
command: "python3 {control_dir}/check.py --domain {params.domain} --infra {params.infra}"
default_mode: ratchet                # block | ratchet | report
owner: craft-dreams-engineering
tests: {pass: tests/pass, fail: tests/fail}
```

- `command` roda com o diretório do projeto (ou do caso de teste) como diretório de trabalho; sem shell;
  `{control_dir}` e `{params.<nome>}` são substituídos.
- **Saída:** JSON em stdout `{"norm","control","norm_hash","violations":[{"file","line","message"}]}`.
  Código 0 = zero violações; 1 = uma ou mais; 2 = erro do controle (parâmetro, ferramenta ausente).
- `kind: judgment` (agente revisor) só pode ser adotado em `report`; nunca é o único controle de uma norma em `block`.
- `active` exige `tests/pass` (0 violações) e `tests/fail` (≥ 1) verdes no CI deste repositório.

### 2.3 Registro de decisão no projeto — `.aora/norms.yaml`

```yaml
controls_repo: {repository: Craft-dreams/aora-controls, ref: <sha>}   # versão fixada do runner e dos controles
norms:
  - norm: ARCH-LAYERS-001
    norm_hash: "<hash da norma quando a decisão foi tomada>"
    control: ARCH-LAYERS-001-py-ast          # deste repositório, ou
    # command: "python3 -m pytest tests/architecture/test_x.py --aora-json"   # controle do projeto
    mode: ratchet
    params: {domain: src/app/domain, infra: src/app/infrastructure}
    decided_at: 2026-10-28
    decided_by: <responsável>
    reason: "<por que este controle, neste modo>"
baseline: .aora/baseline.json
exceptions: .aora/exceptions.yaml
```

Cada entrada é uma decisão consciente. Trocar controle ou modo = nova entrada (a antiga fica com `superseded_at`),
nunca edição silenciosa. É este arquivo que responde "de onde veio esta regra do linter" e alimenta a cobertura.

### 2.4 Runner — `aora-controls`

- `check --project <dir>`: lê `norms.yaml`, resolve cada controle (daqui ou `command` do projeto), executa, aplica
  exceções (`path` glob, `expires`; vencida = erro), aplica o modo contra `baseline.json`. Falha se `block` tem
  violação, `ratchet` cresceu, controle devolveu 2, controle/norma não existe ou não é `active`, ou exceção venceu.
- `baseline --project <dir>`: grava contagens por norma; recusa aumentar (`--init` só sem baseline).
- `coverage --project <dir> [--hub-norms <json>]`: lista norma × controle × modo e marca `outdated` quando o
  `norm_hash` do registro difere do hash atual exportado pelo Hub (`validate.py --profile hub --json`). O JSON do Hub é
  passado como arquivo; este repositório nunca lê o Hub.
- Só biblioteca padrão do Python.

### 2.5 Distribuição

Projeto fixa `controls_repo.ref` e, no CI, faz checkout público deste repositório nesse `ref` (ou `pip install
git+https://…@<ref>`), depois `aora-controls check --project .`. Sem credencial.

### 2.6 Segurança do repositório público

Secret scanning e push protection ligados; CI roda gitleaks; exemplos de teste são sintéticos; nenhum nome de máquina,
IP, caminho de usuário, log real, texto de norma ou código de projeto. Revisão de PR confere isso explicitamente.

## 3. Alternativas rejeitadas

- **Controles no Hub** (rev. 1 da ADR-0002 do Hub): mistura norma e ferramenta; norma passaria a depender da ferramenta.
- **Só nos projetos:** duplica implementação e impede medir cobertura entre projetos.
- **Pacote publicado (PyPI/npm):** mais um artefato a versionar; checkout público por SHA já dá versão e proveniência.
- **Repositório privado:** exigiria credencial de leitura em cada CI; o conteúdo é genérico e o operador decidiu abrir.

## 4. Consequências

- A rastreabilidade fica distribuída: norma (Hub) ← hash → decisão (projeto) → controle (aqui ou projeto). A cobertura
  junta as três pontas a partir de arquivos, sem acesso cruzado entre repositórios no CI.
- Uma norma pode existir sem controle; isso aparece na cobertura como lacuna, não como erro.
- Mudança de norma invalida o `norm_hash` e marca os controles como `outdated` até alguém revalidar.
