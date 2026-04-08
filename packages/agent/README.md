# @ququ/agent

QuQu Persona Agent / Harness package.

## Responsibility

This package owns all code related to:
- persona runtime contract
- context building
- trace artifacts
- remote H20 job orchestration
- offline eval artifacts
- live/offline inference trace shaping
- bad-case export shaping
- eval/live LLM runner scripts

## Main paths

- `src/personaRuntime.ts`
- `src/personaContextBuilder.ts`
- `src/personaArtifacts.ts`
- `src/evalArtifacts.ts`
- `src/remoteJobs.ts`
- `src/inferenceTrace.ts`
- `src/personaExport.ts`
- `scripts/evals/`

## Notes

`packages/player` should treat this package as the backend/harness domain layer, and keep UI/admin/frontend concerns inside `packages/player` only.
