# Global Task Manager

## Current Tasks

| ID   | Task Name | Priority (1-5) | Phases (Done/Total) | Status | Dependencies | Rules Required | Link to `main.md` |
| :--- | :---- | :---- | :--- | :---- | :--- | :---- | :---- |
| T010 | WhisperX Speaker Diarization | 2 | 0/5 | PLANNING | - | task-documentation | [main.md](active/T010-whisperx-diarization/main.md) |
| T011 | Knowledge Base Capture System | 1 | 6/6 | ACTIVE | - | - | [main.md](active/T011-knowledge-base-capture/main.md) |
| T012 | KB Transcription Architecture + Zoom | 2 | 2/3 | ACTIVE | - | task-documentation | [main.md](active/T012-kb-zoom-meetings/main.md) |
| T014 | Cap AI Markers for Intra-Segment Editing | 3 | 0/4 | PLANNING | T013 | - | [main.md](planning/T014-cap-ai-markers/main.md) |
| T019 | KB Prompt Quality Feedback System | 2 | 4/4 | COMPLETE | - | - | [main.md](completed/T019-prompt-quality-feedback/main.md) |
| T020 | KB Posting Queue Extension | 1 | 0/4 | PLAN_REVIEW | - | - | [main.md](active/T020-kb-posting-queue-extension/main.md) |

## Notes
- Priority: 1=Highest, 5=Lowest
- For dependencies, use format: `T00X` or `T00X#PY` for phase-specific dependencies
- Status values: PLANNING, ACTIVE, ONGOING, BLOCKED, PAUSED
- For ongoing tasks without distinct phases, use "Ongoing" in the "Phases" column

## Recently Completed (2026-02-02)
- T018: KB Missing Analyses Detection - 4 phases: core detection, CLI display, batch execution, integration & polish ([main.md](completed/T018-kb-missing-analyses/main.md))

## Recently Completed (2026-02-01)
- T017: KB Decimal & Analysis Configuration UI - 4 phases: decimal list/view, add decimal, edit decimal, polish & CLI flags ([main.md](completed/T017-kb-decimal-config/main.md))

## Completed (2026-01-31)
- T016: KB Video Pipeline Integration - 4 phases: video discovery with smart matching, file reorganization, dashboard videos tab, async transcription queue ([main.md](completed/T016-kb-video-pipeline/main.md))
- T015: KB Serve - Action Queue Dashboard - 6 phases: core server, compound analysis, config-driven actions, file inbox, browse mode, server deployment ([main.md](completed/T015-kb-serve-dashboard/main.md))
- T013: Cap Recording Auto-Clean - `kb clean` command with LLM analysis, trigger phrases, interactive review, soft-delete ([main.md](completed/T013-cap-clean/main.md))

## Recently Archived (2025-01-16)
- T002: UI Implementation
- T005: Fabric Integration
- T006: Settings and Configuration
- T007: Packaging and Deployment
- T008: Testing and Quality Assurance
- T009: Meeting Summary Feature

All archived due to project evolution - app now focuses on daemon mode with whisper.cpp backend.
