# oatrta

Pacote de skills para arquivos `AGENTS.md`: auditar, refatorar e criar, seguindo o guia
[Writing an effective AGENTS.md](https://aaif.io/blog/writing-an-effective-agents-md) (AAIF).

| Skill | Serviço | Altera arquivos? |
|---|---|---|
| `agents-md-audit` | Nota 0 a 100, blockers, veredito linha a linha, lacunas provadas pelo repo | Não |
| `agents-md-refactor` | Aplica o audit: corta ruído, torna regras vagas exatas, corrige comandos e paths, divide root e nested | Sim, só AGENTS.md |
| `agents-md-create` | Cria o root e os nested necessários a partir de evidência do repo e perguntas ao mantenedor | Sim, só arquivos novos |

Fluxo: `audit` decide o próximo passo. Nota baixa com conteúdo aproveitável vai para `refactor`.
Sem arquivo, ou faltando nested, vai para `create`. `refactor` e `create` rodam o rubric de novo
no final.

## Princípio

Um único teste para cada linha: o agente agiria diferente por ter lido isso? Se não, sai.
O guia cita evidência de que arquivos gerados por LLM rendem menos que os escritos por
desenvolvedores, então as skills nunca inventam: cada linha vem de um arquivo do repo ou de uma
resposta do mantenedor.

## Estrutura

```
shared/                      fonte única
  guide.md                   critérios, rubric (A a G), blockers (B1 a B4), vereditos
  scan_agents_md.py          scanner determinístico, só stdlib
scripts/sync_shared.py       copia shared/ para dentro de cada skill
skills/
  agents-md-audit/           SKILL.md, references/report-template.md
  agents-md-refactor/        SKILL.md
  agents-md-create/          SKILL.md, references/template.md
.claude-plugin/              plugin.json e marketplace.json (Claude Code e Copilot CLI)
```

Cada skill carrega a sua cópia de `guide.md` e do scanner para funcionar instalada sozinha.
Edite sempre em `shared/` e rode `python scripts/sync_shared.py` (`--check` para CI).

## Instalação

Claude Code:

```
/plugin marketplace add ppedr/oatrta
/plugin install oatrta@oatrta
```

GitHub Copilot CLI:

```
copilot plugin marketplace add ppedr/oatrta
copilot plugin install oatrta@oatrta
```

Os dois leem o mesmo `.claude-plugin/marketplace.json`.

Sem plugin: copie as pastas de `skills/` para `.claude/skills/` (lido pelo Claude Code e pelo
Copilot), `.github/skills/` (Copilot) ou, para uso pessoal, `~/.claude/skills/` e
`~/.copilot/skills/`.

O scanner exige Python 3.

## Scanner

```
python shared/scan_agents_md.py <repo> --format md
```

Levanta fatos, não dá nota: arquivos AGENTS.md e tamanho, comandos que não resolvem (script npm,
target make, wrapper), paths inexistentes, frases genéricas, prosa de overview, headings vazios,
árvores de diretório, possíveis segredos, outros arquivos de instrução (CLAUDE.md, Copilot,
Cursor), diretórios com manifesto e candidatos a AGENTS.md nested. A nota é dada pela skill com
o rubric de `guide.md`.

## Rubric

| Dimensão | Pts |
|---|---|
| A Densidade de sinal | 20 |
| B Comandos | 15 |
| C Boundaries | 15 |
| D Definition of done | 15 |
| E Convenções concretas | 10 |
| F Acurácia | 15 |
| G Topologia e enforcement | 10 |

Blockers (segredo, comando obsoleto, path obsoleto, contradição) limitam a nota a C.
