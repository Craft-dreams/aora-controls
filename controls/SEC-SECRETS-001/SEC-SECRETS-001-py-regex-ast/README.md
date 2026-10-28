# SEC-SECRETS-001-py-regex-ast

Regex and AST-based secret scanning control for codebases.

## Norma

- **Norma:** `SEC-SECRETS-001`
- **Hash da norma (`norm_hash`):** `"pending"`. O placeholder `"pending"` será preenchido quando o Hub exportar o hash oficial (`validate.py --profile hub --json`); o runner trata `"pending"` como "não validado".

## O que detecta

1. **Literais de segredo conhecidos** em arquivos versionados:
   - Chaves privadas PEM (`-----BEGIN ... PRIVATE KEY-----`)
   - Chaves de acesso AWS (`AKIA[0-9A-Z]{16}`)
   - Tokens de API comuns (`sk-[A-Za-z0-9]{20,}`)
   - GitHub Personal Access Tokens (`ghp_[A-Za-z0-9]{36}`)
   - Atribuições suspeitas no código (`(password|senha|secret|token|api_key) = "<literal com 8+ caracteres>"`)

2. **Vazamento de segredos em logs** (via AST Python):
   - Chamadas a `print(...)`, `logger.<method>(...)` ou funções de logging passando variáveis cujo identificador contenha termos como `password`, `senha`, `secret`, `token` ou `api_key`.

## O que NÃO detecta (não substitui gitleaks)

- **Histórico git:** Este controle analisa apenas a árvore de trabalho atual do checkout (`working tree`), não varre commits anteriores nem o histórico completo de branches/tags (para isso utilize ferramentas dedicadas como `gitleaks` no CI).
- **Segredos dinâmicos ou indiretos:** Valores recuperados de cofres externos ou variáveis de ambiente que sejam expostos indiretamente em tempo de execução via interpolação de strings complexas, objetos serializados (`repr(obj)`), dicionários ou cabeçalhos HTTP.
- **Segredos codificados ou ofuscados:** Segredos em Base64, hexadecimais puros ou hashes sem o prefixo conhecido.
- **Binários:** Arquivos compilados, imagens, arquivos compactados ou dados binários não são inspecionados por entropia.
