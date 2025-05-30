# Global Task Manager

## Current Tasks

| ID   | Task Name | Priority (1-5) | Phases (Done/Total) | Status | Dependencies | Rules Required | Link to `main.md` |
| :--- | :---- | :---- | :--- | :---- | :--- | :---- | :---- |
| T002 | UI Implementation | 2 | 3/4 | ACTIVE | T001 | task-documentation | [main.md](active/T002-ui-implementation/main.md) |
| T005 | Fabric Integration | 3 | 0/4 | ACTIVE | T002, T004 | task-documentation | [main.md](active/T005-fabric-integration/main.md) |
| T006 | Settings and Configuration | 3 | 0/4 | PLANNING | T001, T002, T004 | task-documentation | [main.md](active/T006-settings-and-configuration/main.md) |
| T007 | Packaging and Distribution | 4 | 0/3 | PLANNING | T001, T002, T003, T004, T005, T006 | task-documentation | [main.md](active/T007-packaging-and-distribution/main.md) |
| T008 | Testing and Refinement | 3 | 0/5 | PLANNING | T001, T002, T003, T004, T005, T006 | task-documentation | [main.md](active/T008-testing-and-refinement/main.md) |
| T009 | Meeting Summary Feature | 3 | 2/5 | ACTIVE | T002#P3, T004 | task-documentation, code-conventions, project-architecture | [main.md](active/T009-meeting-summary-feature/main.md) |

## Notes
- Priority: 1=Highest, 5=Lowest
- For dependencies, use format: `T00X` or `T00X#PY` for phase-specific dependencies
- Status values: PLANNING, ACTIVE, ONGOING, BLOCKED, PAUSED
- For ongoing tasks without distinct phases, use "Ongoing" in the "Phases" column 