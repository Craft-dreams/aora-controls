# CONFIG-ENV-001-py-ast

AST-based control enforcing that core business layers (domain and application) do not read environment variables or `.env` files directly.

## Norma

- **Norma:** `CONFIG-ENV-001`
- **Hash da norma (`norm_hash`):** `"pending"`. O placeholder `"pending"` será preenchido quando o Hub exportar o hash oficial (`validate.py --profile hub --json`); o runner trata `"pending"` como "não validado".

## Justificativa

Camadas de domínio e aplicação devem ser puras e receber suas configurações explicitamente via parâmetros, objetos de valor ou injeção de dependência na camada de infraestrutura/composição. O acesso direto a variáveis de ambiente espalha dependências implícitas e dificulta testes unitários.

## O que detecta

Nos pacotes configurados em `--packages` (padrão: `app/domain,app/application`):
- Acesso a `os.environ` ou `os.getenv`
- Importações diretas de `environ` ou `getenv` do módulo `os`
- Importações ou chamadas de `dotenv` ou `load_dotenv()`
- Indexação direta em `environ[...]`

## O que NÃO detecta

- Acesso a variáveis de ambiente através de wrappers ou bibliotecas de terceiros não nomeadas `os` ou `dotenv` (ex.: leitura indireta via `pydantic-settings` ou `dynaconf` instanciados em outro lugar).
- Variáveis de ambiente lidas em subprocessos (`subprocess.run(..., env=...)`).
- Arquivos fora dos diretórios configurados em `--packages`.
