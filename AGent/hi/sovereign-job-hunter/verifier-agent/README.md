# Verifier Agent

## Role

The `verifier-agent` checks whether every generated resume claim is supported by local evidence.

## Base Sample

Use `../llm-auditor` as the implementation reference.

## Adaptations Needed

- replace web-first truth checking with local-evidence-first verification
- allow web verification only for public company or technology facts
- reject embellished experience duration, impact claims, or unsupported tool usage
- produce `VerifiedResumePatch`

## Core Checks

- does the claim appear in the resume, cover letter, or project evidence?
- is the time range accurate?
- is the metric supported or only estimated?
- is the technology named explicitly in evidence?
- should the claim be softened instead of removed?

## Immediate Risk To Normalize

The current resume text says `April 2025 - Present (1 year)`. On March 4, 2026, that duration is not yet a full year. This is the kind of issue the verifier should catch automatically.
