## description: Task management and documentation protocols for AI agents.

## Part 1: Initiating a New Task (Lead Developer & AI Handoff)

This protocol outlines how new tasks, features, or issues are captured by the Lead Developer and then handed off to you, the AI agent, for formalization and management.

### 1.1. Idea/Issue Capture (Lead Developer Action)

1.  **Create Inbox File:** The Lead Developer will create a new markdown file in the `tasks/inbox/` directory (e.g., `tasks/inbox/brief-description-slug.md`).
2.  **Content:** This file will briefly describe the idea, problem, or feature request.

### 1.2. AI Agent Tasking (Lead Developer Action)

1.  The Lead Developer will instruct you (the AI agent) to process an item from `tasks/inbox/` or will provide a description for you to place into a new inbox file.
2.  You will then follow **"Part 2: AI Task Formalization & Management Protocol"** to formalize the item into a structured task, create all required documentation, and update the Global Task Manager (GTM).

---

## Part 2: AI Task Formalization & Management Protocol (AI Agent Actions)

Follow these steps sequentially to process inbox items, create and manage task documentation, and update the Global Task Manager (GTM). Always refer to **Section 7: Reference Materials** for structural definitions (Core Principles, GTM, Statuses, Tools).

### Step 1: Inbox Item Intake & Preparation

1.1. **Identify/Create Inbox Item:**
_ **If the Lead Developer points you to an existing file in `tasks/inbox/`**: Acknowledge the file.
_ **If the Lead Developer describes a new task/issue for the inbox**: 1. Create a new markdown file in `tasks/inbox/`. Name it appropriately (e.g., `tasks/inbox/short-description-slug.md`). 2. Write the Lead Developer's description into this file. 3. Confirm creation of the inbox file.
1.2. **Confirm Readiness:** State that the inbox item is identified/created and you are ready to proceed to Step 2 (Research & Discovery).

### Step 2: Research & Discovery

2.1. **Analyze Inbox Item:** Thoroughly read and understand the content of the identified inbox item.
2.2. **Consult GTM:**
_ Open and review `tasks/global-task-manager.md`.
_ Note existing tasks, their statuses, and dependencies for overall project context.
_ Identify the highest current Task ID to determine the next available ID.
2.3. **Review Related Tasks (if applicable):** If the inbox item mentions or implies connections to existing tasks, review their respective `main.md` files for deeper understanding.
2.4. **Examine Project Structure:** Search the current project/repository for relevant files, code sections, or existing documentation related to the inbox item's content.
2.5. **Identify Applicable Rules:**
_ Execute the script provided in **Section 7.4 (TOOLS SECTION)**. \* From the output, determine the list of relevant rule file basenames.
2.6. **Synthesize Findings:** Consolidate all gathered information.
2.7. **Confirm Readiness:** State that research and discovery are complete and you are ready to proceed to Step 3 (Documentation & GTM Update).

### Step 3: Task Documentation & GTM Update

3.1. **Assign Task ID:** Determine the next sequential Task ID (incrementing the highest ID found in Step 2.2).
3.2. **Create Task Directory:**
_ Create a new directory within `tasks/active/`.
_ Name it `TXXX-task-name-slug` (e.g., `T001-new-feature-slug`), replacing `TXXX` with the new Task ID and creating an appropriate slug (lowercase, spaces to hyphens).
3.3. **Create and Populate `main.md`:**
_ Copy the content from the template file located at `tasks/main-template.md` into a new `main.md` file inside the newly created task directory.
_ Using your findings from Step 2, meticulously populate all non-optional sections of this `main.md` file.
_ Define initial phases in the "Phases Breakdown" section, providing objectives for each. Document phase details either inline or by creating initial `phases/phase-N.md` files (see Section 7.1 and the template structure for guidance).
3.4. **Update Global Task Manager (GTM):**
_ Open `tasks/global-task-manager.md`.
_ Add a new row to the "Current Tasks" table.
_ Populate all columns according to the **GTM Table Structure (Section 7.2)**. Ensure information (Task Name, Dependencies, Rules Required, Link) aligns with the newly created `main.md`.
_ Set the initial **Status** to `PLANNING`.
3.5. **Archive Inbox Item:**
_ Move the original inbox markdown file (from Step 1) into a new subfolder named `_inbox_source/` within the task directory created in Step 3.2.
3.6. **Confirm Completion:** State that the task has been formalized, `main.md` and the task directory are created, the GTM is updated, the inbox item is archived, and you await further instructions or the next task.

### Step 4: Ongoing Task Management & Updates (Perform When Instructed)

4.1. **Receive Instructions:** The Lead Developer may instruct you to update a specific task, or this step may be part of active work on a task.
4.2. **Maintain Documentation:**
_ Update the relevant task's `main.md` file (and any `phases/phase-N.md` files if used).
_ Reflect current progress, phase status changes, completed objectives, new findings, or refined details.
4.3. **Update GTM:**
_ Open `tasks/global-task-manager.md`.
_ Promptly update the corresponding task's row to reflect changes in:
_ **Phases (Done/Total)**
_ **Status** (e.g., `ACTIVE`, `BLOCKED`, `PAUSED`) \* **Dependencies** (if new ones are discovered or resolved)
4.4. **Provide Feedback:** Offer feedback on task complexity, feasibility, discovered dependencies, or clarity of requirements.
4.5. **Confirm Updates:** State that the requested updates to task documentation and/or GTM have been completed.

### Step 5: Task Completion & Archival (Perform When Instructed)

5.1. **Receive Instruction:** The Lead Developer will instruct you when a task is completed or needs to be archived.
5.2. **For COMPLETED Tasks:** 1. Verify that all phases in the task's `main.md` are marked as complete and all documentation is final and accurate. 2. Open `tasks/global-task-manager.md` and remove the entire row for the completed task from the "Current Tasks" table. 3. Move the entire task directory (e.g., `tasks/active/TXXX-task-name-slug/`) to the `tasks/completed/` directory. 4. Confirm task completion and archival.
5.3. **For ARCHIVED Tasks (Not Pursued/Obsolete):** 1. Open `tasks/global-task-manager.md` and remove the entire row for the task from the "Current Tasks" table. 2. Move the entire task directory to the `tasks/archived/` directory. 3. Confirm task archival.

### Section 7: Reference Materials

#### 7.1. Core Principles & Structure Summary

- **Global Task Manager (GTM):** `tasks/global-task-manager.md` is the central hub.
- **Task IDs:** Unique sequential ID (e.g., `T001`).
- **Directory Structure:**
  - Status Directories: `tasks/inbox/`, `tasks/active/`, `tasks/ongoing/`, `tasks/completed/`, `tasks/archived/`.
  - Task Directory: `TXXX-task-name-slug` (lowercase, spaces to hyphens) within status directory.
  - Task Document: `main.md` inside task directory.
  - Inbox Source: Original inbox file moved to `_inbox_source/` within task directory post-processing.
- **Phase Documentation:**
  - Tasks _must_ be broken into distinct phases (guideline: completable in a few days).
  - Detailed phase info (Objectives, Est. Time, Resources, Dependencies) must be documented either inline in `main.md` (see template for structure) or in separate `phases/phase-N.md` files.
  - Complex phases can have additional subdocuments (e.g., `phases/phase-1-detailed-steps.md`).
  - Each phase document/section _must_ include: Phase Objectives, Estimated Time, Resources Needed, Dependencies (`T00X#PY` format for phase-specific).
- **`main.md` Template Location:** `tasks/main-template.md` (You must copy and populate this for each new task).

#### 7.2. Global Task Manager Table Structure (`tasks/global-task-manager.md`)

The "Current Tasks" table must have the following columns:

| ID  | Task Name | Priority (1-5) | Phases (Done/Total) | Status | Dependencies (e.g., `T00X`, `T00Y#P1`) | Rules Required | Link to `main.md` |
| :-- | :-------- | :------------- | :------------------ | :----- | :------------------------------------- | :------------- | :---------------- |
| ... | ...       | ...            | ...                 | ...    | ...                                    | ...            | ...               |

- **Phases (Done/Total):** For `ONGOING` tasks, use "Ongoing" or similar, not a ratio.
- **Dependencies:** Use `-` if none.
- **Priority:** 1=Highest, 5=Lowest.

#### 7.3. Task Statuses

- **INBOX**: Initial capture. Not typically in GTM table.
- **PLANNING**: Defined, phases being detailed. Awaiting active work.
- **ACTIVE**: Currently being worked on.
- **ONGOING**: Recurring task, actively maintained.
- **BLOCKED**: Progress halted due to unmet dependencies.
- **PAUSED**: Work temporarily stopped, may resume later.
- **COMPLETED**: All phases finished. Task directory moved to `tasks/completed/`. Removed from GTM table.
- **ARCHIVED**: Decided not to pursue or obsolete. Task directory moved to `tasks/archived/`. Removed from GTM table.

#### 7.4. TOOLS SECTION (Identifying Applicable Rules)

To identify relevant rule filenames for the "Rules Required" column (in GTM and `main.md`):

```bash
for file in .cursor/rules/*.mdc; do
  echo "File: $(basename "$file")";
  grep -m 1 "description:" "$file" | awk -F': ' '{print "Description: " $2}';
  echo "";
done
```
