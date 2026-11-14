# AGENTS.md starting templates

These are scaffolds, not forms. **Delete every section that has nothing consequential to say.**
A finished file with two sections is fine. Lines in angle brackets are instructions to you and
never ship.

## Root file

```markdown
# AGENTS.md

## Commands
<Exact, with working directory. Explain non-obvious tool choices. First, because agents come
back to it most.>
- Install: from the repo root, `make bootstrap` (not `npm install`; it also builds the codegen).
- Unit tests for one package: from `packages/<name>`, `npm test`.
- Full check: from the repo root, `make ci`.

## Layout
<Only what names do not reveal. Ownership, shared code, the real entry point. No tree.>
- `packages/core` is shared by every app; changes there need the full test suite.
- Feature flags live in `config/flags.yaml`, not in the service configs.

## Rules
<Project-specific and concrete. Name the canonical file.>
- New HTTP handlers follow `services/api/internal/http/orders_handler.go`.
- `domain/` must not import from `infra/`. `make lint` checks this.

## Generated and restricted files
<Path, and the source to edit instead. Then what needs approval, apart from what is never
allowed. Only rules the repo proves or the maintainer gave.>
- `gen/` is generated. Edit `proto/` and run `make generate`.
- Do not change files under `migrations/` that are already merged; add a new migration.
- Ask first: upgrading dependencies, changing the public API in `api/openapi.yaml`, editing
  `.github/workflows/`.
- Never: skip or delete a failing test to get a green run; push or open a pull request.

## Done means
<What to run while iterating, what to run before finishing, how it scales.>
- While iterating: the unit tests of the package you touched.
- Before finishing: `make ci` from the repo root.
- Touching `packages/core` or `proto/`: also run `make test-integration`.

## More
<Pointers only.>
- Release process: `docs/releasing.md`.
```

## Nested file

Only area-specific content. Nothing that the root already says.

```markdown
# AGENTS.md (services/billing)

- Java 21, built with the Gradle wrapper in this directory: `./gradlew check`.
- Integration tests need the local stack: `docker compose up -d` here, then
  `./gradlew integrationTest`.
- Flyway migrations in `src/main/resources/db/migration` are append-only.
- Money is `BigDecimal` with `MoneyUtils.round`; see `InvoiceCalculator.java`.
```

## Before you ship: delete if you see

- "This project is a ..." or any stack description
- A toolchain version that `go.mod`, `engines`, `.nvmrc` or similar already pins
- Content only one tool understands (its slash commands, settings): it goes in that tool's file
- A directory tree
- "clean code", "best practices", "follow existing patterns", "be careful"
- A heading with no content
- A paragraph copied from README or CONTRIBUTING
- A command without a working directory in a multi-project repo
- A command you did not resolve against a real script or target
