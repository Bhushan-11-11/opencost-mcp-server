# Execution Agent

## Role

The `execution-agent` handles gated submission workflows after verification passes.

## Base Sample

Use `../parallel_task_decomposition_execution` as the implementation reference.

## Adaptations Needed

- replace mock broadcast tools with application tools
- add approval gates before submission
- keep a durable submission ledger
- support dry-run mode before live submission

## Inputs

- `JobManifest`
- `ApplicationPacket`
- operator approval state

## Outputs

- `ApplicationLedgerEntry`
- provider-specific submission results
- failure reasons for retry or manual action

## Current Implementation

- `agent.py`: approval-gated execution with durable `jsonl` ledger
- `render_pdfs.py`: renders resume and cover letter PDFs from `application_packet.json`

## Suggested Connectors

- StackOne
- Workday
- Greenhouse
- Lever
- company career portals where API or browser automation is available
