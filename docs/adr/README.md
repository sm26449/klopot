# Architecture Decision Records

Short, numbered documents that capture one decision each: the context,
the options considered, what we chose and why, and what it costs.
They are written once and never edited after acceptance — a later
decision that changes course gets a new ADR that supersedes the old one.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-brand-identity-klopot.md) | Product name, visual identity and where each colour is used | Accepted |
| [0002](0002-os-native-theme-families.md) | Optional OS-native theme families (macOS/Windows/GNOME/KDE) | Accepted |

## Format

```
# ADR-NNNN — Title
Status: Proposed | Accepted | Superseded by ADR-MMMM
Date: YYYY-MM-DD

## Context        — the forces at play, in a few paragraphs
## Decision       — what we decided, stated plainly
## Consequences   — what gets easier, what gets harder, what we must do next
## Alternatives   — what else we considered and why not
```

Keep an ADR under two screens. Link to the code or docs that implement
it instead of repeating them.
