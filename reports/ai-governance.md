# AI Governance

## Purpose
- Establish a single source of truth for each capability.
- Prefer refactor and reuse over creating duplicate modules.
- Keep all new features behind feature flags.
- Preserve backward compatibility with current workflows.
- Pair every new module with documentation and tests.

## Governance Rules
1. Do not create a new module when an equivalent module already exists.
2. Prefer refactoring the existing module before adding a new one.
3. Every new feature must be toggleable with a feature flag.
4. Preserve backward compatibility for the existing publishing workflow.
5. Require tests and documentation for every new module.
