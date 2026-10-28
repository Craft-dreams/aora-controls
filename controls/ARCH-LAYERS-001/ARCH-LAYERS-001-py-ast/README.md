# ARCH-LAYERS-001-py-ast

AST-based architectural boundary verifier ensuring that domain layer packages do not import from infrastructure layer packages.

## Norma

- **Norma:** `ARCH-LAYERS-001`
- **Hash da norma (`norm_hash`):** `"pending"`. O placeholder `"pending"` será preenchido quando o Hub exportar o hash oficial (`validate.py --profile hub --json`); o runner trata `"pending"` como "não validado".

## O que detecta

- Comandos estáticos de importação Python (`import <infra>...`, `from <infra> import ...`) localizados dentro dos arquivos do pacote de domínio configurado em `--domain` (padrão: `app/domain`) que apontam para o pacote de infraestrutura configurado em `--infra` (padrão: `app/infrastructure`).
- Importações relativas dentro do pacote de domínio que resolvem para o pacote de infraestrutura.

## O que NÃO detecta

- Importações dinâmicas em tempo de execução via `importlib.import_module()`, `__import__()`, etc.
- Injeção de dependências ou carregamento dinâmico via reflexão/metaclasses.
- Arquivos que não sejam código fonte Python (`.py`).
- Chamadas de rede diretas ou dependências externas sem importação do pacote local de infraestrutura.
