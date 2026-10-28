# Adotando controles em um projeto

Este guia orienta como um projeto adota e executa controles que verificam normas do Knowledge Hub.

## 1. Visão Geral

A governança do Hub opera em quatro etapas:
1. **Norma:** Definida no Knowledge Hub com critério verificável.
2. **Decisão do Projeto (`.aora/norms.yaml`):** O projeto escolhe formalmente qual controle aplicar, em qual modo (`block`, `ratchet`, `report`), data, responsável e justificativa.
3. **Catraca / Baseline (`.aora/baseline.json`):** Para normas adotadas em modo `ratchet`, fixa a contagem máxima de violações toleradas (o número só diminui).
4. **Execução no CI:** O runner `aora-controls` executa os controles, avalia exceções temporárias e falha o build se houver novas violações ou regras quebradas.

---

## 2. Estrutura de Arquivos no Projeto

```
meu-projeto/
├── .aora/
│   ├── norms.yaml          # Registro formal das decisões
│   ├── exceptions.yaml     # Exceções com prazo de expiração (opcional)
│   └── baseline.json       # Contagem de catraca por norma
├── .github/
│   └── workflows/
│       └── ci.yml          # Passo que roda 'aora-controls check'
└── src/
    └── app/...
```

---

## 3. Passo a Passo de Adoção

### Passo 1: Criar o Registro de Decisões (`.aora/norms.yaml`)

Crie o arquivo `.aora/norms.yaml` na raiz do projeto fixando o repositório e a revisão (`ref`) de `aora-controls`:

```yaml
controls_repo:
  repository: Craft-dreams/aora-controls
  ref: "v0.1.0"   # ou um commit sha fixo

norms:
  - norm: ARCH-LAYERS-001
    norm_hash: "pending"
    control: ARCH-LAYERS-001-py-ast
    mode: ratchet
    params:
      domain: src/app/domain
      infra: src/app/infrastructure
    decided_at: "2026-10-28"
    decided_by: "eng-team"
    reason: "Impedir acoplamento direto entre camadas de negócio e infraestrutura"

  - norm: SEC-SECRETS-001
    norm_hash: "pending"
    control: SEC-SECRETS-001-py-regex-ast
    mode: block
    params:
      paths: "src"
      exclude: "tests,.git"
    decided_at: "2026-10-28"
    decided_by: "sec-team"
    reason: "Bloquear segredos em código versionado e logs"

baseline: .aora/baseline.json
exceptions: .aora/exceptions.yaml
```

#### Modos de Execução
- **`block`**: Falha se houver 1 ou mais violações efetivas (não toleradas por exceção).
- **`ratchet`**: Tolerância limitada pelo valor registrado em `baseline.json`. Falha se o número de violações aumentar.
- **`report`**: Executa e reporta violações sem quebrar o CI. (Obrigatório para controles `kind: judgment`).

---

### Passo 2: Inicializar o Baseline (`baseline --init`)

Se o projeto já possui código existente e adotou normas em modo `ratchet`, meça o estado atual e inicialize o baseline:

```bash
aora-controls baseline --project . --init
```

O comando executará os controles configurados e gerará o arquivo `.aora/baseline.json`:

```json
{
  "ARCH-LAYERS-001": 4
}
```

> [!IMPORTANT]
> **A catraca só diminui:** Uma vez inicializado, o comando `aora-controls baseline --project .` só aceita atualizar o arquivo se o número de violações for menor ou igual ao baseline anterior. Se o código introduzir novas violações, o comando recusa o aumento com erro.

Comite o arquivo gerado:
```bash
git add .aora/baseline.json && git commit -m "chore: initialize aora baseline"
```

---

### Passo 3: Cadastrar Exceções Temporárias (`.aora/exceptions.yaml`)

Caso exista um arquivo legado que necessite de dispensa temporária, registre uma exceção formal:

```yaml
- norm: ARCH-LAYERS-001
  path: "src/app/legacy/old_service.py"
  reason: "Módulo legado em refatoração para desacoplamento"
  owner: "tech-lead"
  expires: "2026-12-31"
```

> [!WARNING]
> Exceções vencidas (`expires < data atual`) causam **erro fatal** no comando `check`, forçando a renovação justificada ou a resolução da dívida técnica.

---

### Passo 4: Integrar ao CI

Como o repositório `aora-controls` é público, não são necessárias credenciais ou tokens para executá-lo no CI.

Exemplo de passo no GitHub Actions (`.github/workflows/ci.yml`):

```yaml
name: CI

on: [push, pull_request]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout projeto
        uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Checkout aora-controls
        uses: actions/checkout@v4
        with:
          repository: Craft-dreams/aora-controls
          ref: 'v0.1.0' # ou o SHA fixado em .aora/norms.yaml
          path: .tools/aora-controls

      - name: Executar verificações de governança
        run: |
          PYTHONPATH=.tools/aora-controls/src python3 -m aora_controls check --project . --controls-dir .tools/aora-controls/controls
```

Ou via instalação direta do pacote:

```yaml
      - name: Instalar aora-controls
        run: pip install git+https://github.com/Craft-dreams/aora-controls.git@v0.1.0

      - name: Executar check
        run: aora-controls check --project .
```

---

## 4. Como Registrar Troca de Controle ou Modo

Nunca altere silenciosamente uma decisão existente. Cada alteração representa uma nova decisão consciente de engenharia:

1. No arquivo `.aora/norms.yaml`, marque a decisão anterior como superada com o campo `superseded_at`:
2. Adicione a nova entrada com os novos parâmetros, controle ou modo:

```yaml
norms:
  - norm: ARCH-LAYERS-001
    norm_hash: "pending"
    control: ARCH-LAYERS-001-py-ast
    mode: ratchet
    params: {domain: src/app/domain, infra: src/app/infrastructure}
    decided_at: "2026-10-28"
    decided_by: "eng-team"
    reason: "Adoção inicial com catraca"
    superseded_at: "2026-11-15"

  - norm: ARCH-LAYERS-001
    norm_hash: "pending"
    control: ARCH-LAYERS-001-py-ast
    mode: block
    params: {domain: src/app/domain, infra: src/app/infrastructure}
    decided_at: "2026-11-15"
    decided_by: "eng-team"
    reason: "Débito quitado; promovido a bloqueio estrito"
```

3. Caso a norma tenha migrado para `block`, o baseline dessa norma pode ser removido ou zerado.
