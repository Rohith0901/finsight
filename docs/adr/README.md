# Architecture decision records

Each record explains one decision: the context, the options, what was chosen
and what it costs. The first versions were written during planning (30
September 2026) in the design doc; these files are the maintained copies and
record what was actually built.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-stateless-backend.md) | Stateless backend; all data stays on the phone | Accepted |
| [0002](0002-flutter-native-sms.md) | Flutter UI; SMS read through our own Kotlin channel | Accepted (revised) |
| [0003](0003-inference-in-fastapi.md) | Model inference in FastAPI, portable JSON artifacts | Accepted |
| [0004](0004-encrypted-local-database.md) | SQLCipher through sqflite_sqlcipher | Accepted (revised) |
| [0005](0005-llm-provider-interface.md) | LLM behind a provider interface, local default, verified numbers | Accepted |
| [0006](0006-category-resolution.md) | Category resolution order and correction loop | Accepted (revised) |
| [0007](0007-evaluation-protocol.md) | Evaluation protocol | Accepted; real test set pending |

To change a decision, add a new record that supersedes the old one and update
the table. Don't rewrite history in an accepted record beyond a "Revision" note.

Template:

```markdown
# ADR-00N: Title

Status: Proposed | Accepted | Superseded by ADR-00M
Date: YYYY-MM-DD · Deciders: ...

## Context
## Decision
## Options considered
## Consequences
```
