# @ququ/player

QuQu web frontend / admin console.

## Responsibility

This package owns:
- Next.js app router pages
- admin/evals UI
- API routes that expose the web control plane
- Prisma schema / DB access for the web app
- frontend components and page-level orchestration

## Not owned here

The LLM / runner / harness implementation lives in `../agent`.
Frontend code should import those capabilities from `@ququ/agent/*` instead of re-implementing them locally.
