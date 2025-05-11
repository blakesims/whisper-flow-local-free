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
**Status**: Blocked

**Objectives**:
- Create service for interacting with fabric CLI - **Done** (`app.core.fabric_service.py` created with `FabricService` class)
- Implement pattern listing functionality (`fabric -l`) - **Done** (`list_patterns` method implemented)
- Develop process execution and output capture - **Done** (Using `subprocess.run` with stdin)
- Create error handling for CLI operations - **Done** (Implemented for common subprocess errors, enhanced for API issues)
- Test basic fabric integration - **Blocked** (Underlying `fabric` CLI calls are failing due to an Anthropic API credit issue. `FabricService` itself is likely correct.)

**Actual Time**: ~1 day (Initial service implementation, multiple rounds of testing and refinement)

**Summary of Changes**:
- Created `app.core.fabric_service.py`.
- Implemented `FabricService` class with:
    - `__init__(self, fabric_executable_path="fabric")`
    - `list_patterns(self)`: Executes `fabric -l` and parses plain text output.
    - `run_pattern(self, pattern_name: str, text_input: str)`: Executes `fabric --pattern <pattern_name>` piping `text_input` to stdin. Includes enhanced error detection for API issues.
- Testing revealed that `fabric` CLI execution fails due to an external Anthropic API credit balance problem.

**Estimated Time**: 2 days

**Resources Needed**:
- fabric CLI documentation
- Python subprocess documentation
- CLI integration examples

**Dependencies**:
- T004#P1 completion

### Phase 2: Pattern Selection Interface
**Status**: Not Started

**Objectives**:
- Implement fuzzy search component for pattern selection
- Create pattern selection dialog/modal
- Develop pattern preview functionality if applicable
- Implement keyboard navigation for pattern selection
- Test search performance with large pattern lists

**Estimated Time**: 2 days

**Resources Needed**:
- Fuzzy search library documentation
- Qt dialog implementation examples
- UX guidelines for search interfaces

**Dependencies**:
- Phase 1 completion
- T002#P3 completion

### Phase 3: Workflow Implementation
**Status**: Not Started

**Objectives**:
- Develop workflow for direct transcription paste
- Implement workflow for fabric pattern processing
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