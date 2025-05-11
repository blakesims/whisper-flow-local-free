# Global Task Manager

## Current Tasks

| ID | Task Name | Priority (1-5) | Phases (Done/Total) | Status | Dependencies | Rules Required | Link to `main.md` |
| :--- | :---- | :---- | :--- | :---- | :--- | :---- | :---- |
| T001 | Project Setup and Environment Configuration | 1 | 0/4 | PLANNING | - | task-documentation | [main.md](active/T001-project-setup/main.md) |
| T002 | UI Implementation | 2 | 0/4 | PLANNING | T001 | task-documentation | [main.md](active/T002-ui-implementation/main.md) |
| T003 | Audio Recording Implementation | 2 | 0/4 | PLANNING | T001, T002 | task-documentation | [main.md](active/T003-audio-recording-implementation/main.md) |
| T004 | Transcription Engine Integration | 2 | 0/4 | PLANNING | T001, T003 | task-documentation | [main.md](active/T004-transcription-engine-integration/main.md) |
| T005 | Fabric Integration | 3 | 0/4 | PLANNING | T002, T004 | task-documentation | [main.md](active/T005-fabric-integration/main.md) |
| T006 | Settings and Configuration | 3 | 0/4 | PLANNING | T001, T002, T004 | task-documentation | [main.md](active/T006-settings-and-configuration/main.md) |
| T007 | Packaging and Deployment | 4 | 0/4 | PLANNING | T001, T002, T003, T004, T005, T006 | task-documentation | [main.md](active/T007-packaging-and-deployment/main.md) |
| T008 | Testing and Quality Assurance | 4 | 0/4 | PLANNING | T001, T002, T003, T004, T005, T006, T007 | task-documentation | [main.md](active/T008-testing-and-quality-assurance/main.md) |

## Notes
- Priority: 1=Highest, 5=Lowest
- For dependencies, use format: `T00X` or `T00X#PY` for phase-specific dependencies
- Status values: PLANNING, ACTIVE, ONGOING, BLOCKED, PAUSED
- For ongoing tasks without distinct phases, use "Ongoing" in the "Phases" column 