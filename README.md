# aora-controls

Controles reutilizáveis que **aplicam normas** do Knowledge Hub da Craft-dreams. Cada controle referencia uma norma pelo
`aora.id` e pelo hash do texto dela; a norma vive no Hub, o controle vive aqui ou no projeto que o usa.

**Este repositório é público. Nada sensível entra aqui:** nenhum texto de norma ou conhecimento do Hub, nenhum dado de
projeto, nenhuma credencial, nenhum caminho interno de máquina. Só código genérico de verificação, seus testes com
exemplos sintéticos e a documentação de como um projeto adota um controle. Secret scanning e push protection estão ligados.

## O que há aqui

| Pasta | Conteúdo |
|---|---|
| `controls/<NORM-ID>/<control-id>/` | Um controle: `control.yaml` (descritor), implementação, `tests/pass/` e `tests/fail/` |
| `src/aora_controls/` | Runner `aora-controls` (`check`, `baseline`, `coverage`) que lê o `.aora/norms.yaml` de um projeto |
| `docs/adr/` | Decisões deste repositório |
| `docs/ADOPTING.md` | Como um projeto adota controles (registro de decisão, baseline, CI) |

## Contrato em uma frase

Norma (Hub) → **decisão registrada no projeto** (`.aora/norms.yaml`: norma, hash, controle, modo, data, responsável,
motivo) → controle executado no CI do projeto → resultado em JSON com violações → modo `block` / `ratchet` / `report`.

Veja `docs/adr/0001-controls-outside-the-hub.md` e, no Hub, a ADR-0002.
