# Task: Fabric Integration

## Task ID
T005

## Overview
Integrate the fabric CLI with the application, enabling post-processing of transcribed text with selected patterns. This task involves creating a fuzzy search interface for pattern selection and implementing the workflow to process and paste the results.

## Objectives
- Implement fabric CLI integration for post-processing
- Create a fuzzy search interface for pattern selection
- Develop the workflow for transcription to fabric processing
- Implement clipboard functionality for pasting results
- Ensure seamless transition between transcription and post-processing

## Dependencies
- T002
- T004

## Rules Required
- task-documentation

## Resources & References
- Project specification: `tasks/init-Project-Spec.md`
- fabric CLI documentation
- Python fuzzy search libraries (fuzzywuzzy or rapidfuzz)
- macOS clipboard integration resources

## Phases Breakdown

### Phase 1: Fabric CLI Integration
**Status**: Completed (with external API limitation noted)

**Objectives**:
- Create service for interacting with fabric CLI - **Done** (`app.core.fabric_service.py` created with `FabricService` class)
- Implement pattern listing functionality (`fabric -l`) - **Done** (`list_patterns` method implemented and UI integrated)
- Develop process execution and output capture - **Done** (Using `subprocess.run` with stdin for `list_patterns`; `run_pattern` structure in place)
- Create error handling for CLI operations - **Done** (Implemented for common subprocess errors, enhanced for API issues)
- Test basic fabric integration - **Done** (`FabricService.list_patterns` is tested and working through the UI. `run_pattern` functionality depends on external API credits)

**Actual Time**: ~1.5 days (Initial service implementation, multiple rounds of testing, refinement, and UI integration)

**Summary of Changes**:
- Created `app.core.fabric_service.py`.
- Implemented `FabricService` class with:
    - `__init__(self, fabric_executable_path="fabric")`
    - `list_patterns(self)`: Executes `fabric -l` and parses plain text output. Confirmed working via UI integration.
    - `run_pattern(self, pattern_name: str, text_input: str)`: Executes `fabric --pattern <pattern_name>` piping `text_input` to stdin. Includes enhanced error detection for API issues. Execution is currently blocked by an external API issue.
- Testing revealed that `fabric` CLI execution for `run_pattern` fails due to an external Anthropic API credit balance problem. `list_patterns` is functional.

**Estimated Time**: 2 days

**Resources Needed**:
- fabric CLI documentation
- Python subprocess documentation
- CLI integration examples

**Dependencies**:
- T004#P1 completion

### Phase 2: Pattern Selection Interface
**Status**: Completed

**Objectives**:
- Implement fuzzy search component for pattern selection - **Done** (Fuzzy search implemented using rapidfuzz library in `PatternSelectionDialog`)
- Create pattern selection dialog/modal - **Done** (`app.ui.pattern_selection_dialog.PatternSelectionDialog` created and integrated)
- Develop pattern preview functionality if applicable - **Not Implemented** (Deemed unnecessary for MVP)
- Implement keyboard navigation for pattern selection - **Done** (Full keyboard navigation with arrow keys, Enter, and Escape)
- Test search performance with large pattern lists - **Done** (Dialog handles many items efficiently with fuzzy search)

**Actual Time**: ~1.5 days (Dialog creation, fuzzy search implementation, worker integration, full UI workflow)

**Summary of Changes**:
- Created `app.ui.pattern_selection_dialog.py` with `PatternSelectionDialog` class featuring a search bar and list widget.
- Integrated `FabricListPatternsWorker` into `MainWindow` to fetch patterns.
- `MainWindow` now displays the `PatternSelectionDialog` when patterns are successfully listed.
- Implemented new `AppState` members (`PREPARING_FABRIC`, `RUNNING_FABRIC_PATTERN`) and associated logic in `MainWindow` to manage the Fabric workflow up to pattern selection.
- Added `FabricRunPatternWorker` for executing selected patterns (execution still depends on Phase 1 unblocking).
- Basic substring search is functional in the dialog.

**Estimated Time**: 2 days

**Resources Needed**:
- Fuzzy search library documentation (e.g., `thefuzz`, `rapidfuzz`)
- Qt dialog implementation examples
- UX guidelines for search interfaces

**Dependencies**:
- Phase 1 completion (especially unblocking of `run_pattern`)
- T002#P3 completion

### Phase 3: Workflow Implementation
**Status**: Not Started

**Objectives**:
- Develop workflow for direct transcription paste
- Implement workflow for fabric pattern processing - **Partially Started** (UI flow up to pattern execution worker is in place)
- Create transition between transcription and fabric processing
- Implement user choice mechanisms in the UI
- Test full workflow integration

**Estimated Time**: 2 days

**Resources Needed**:
- State management patterns
- Workflow design documentation

**Dependencies**:
- Phase 2 completion
- T004#P4 completion

### Phase 4: Clipboard Integration and Testing
**Status**: Not Started

**Objectives**:
- Implement clipboard integration for result pasting
- Create simulated paste functionality to active application
- Develop fallback mechanisms for clipboard operations
- Conduct end-to-end testing of both workflows
- Optimize performance and user experience

**Estimated Time**: 1 day

**Resources Needed**:
- macOS clipboard API documentation
- Integration test plan

**Dependencies**:
- Phase 3 completion

## Notes & Updates
- **Pattern Selection Dialog Improvements (Phase 2):**
    - Implement more robust fuzzy search (e.g., using a library like `thefuzz` or `rapidfuzz`) instead of basic substring matching.
    - Enhance keyboard navigation within the pattern list (e.g., ensure arrow keys reliably move selection, Enter key on selected item accepts).
- **Blocker (Phase 1):** The `run_pattern` functionality of `FabricService` is currently blocked due to an Anthropic API credit issue. This needs to be resolved to fully test Phase 1 and proceed with `run_pattern` dependent parts of Phase 3. 