# Power Socket — ROADMAP 2

> This is the implementation roadmap for the agreed TUI, profile, shared context, and provider-session redesign.
> The original ROADMAP.md is historical and must remain unchanged.
> Do not mark an item complete until its implementation and relevant tests have passed.
> Do not publish or push changes unless the user explicitly asks.

## Scope and project rules

- [ ] Redesign the existing Textual TUI without replacing the project or discarding existing features.
- [ ] Support Windows, Linux, and Android through Termux. macOS is out of scope.
- [ ] Adapt layout to terminal dimensions; do not optimize exclusively for mobile or desktop.
- [ ] Keep resource usage modest. Avoid model downloads, benchmarks, server startup, heavyweight dependencies, and broad filesystem scans.
- [ ] Preserve existing chats, profiles, export settings, credentials, and user files.
- [ ] Do not modify ROADMAP.md.
- [ ] Do not commit or push unless explicitly requested.
- [ ] Keep user-selected files at their original paths; do not silently copy them into application storage.
- [ ] Missing, unreadable, or invalid selected paths must show a clear error and allow the user to select the file/folder again. Never silently substitute another file.

## Agreed product behavior

### Navigation and responsive TUI

- [ ] Chat is the primary page.
- [ ] Add a compact menu button at the upper-left.
- [ ] The menu opens as a popup; it must not permanently consume chat width.
- [ ] Popup navigation includes Chat, Settings, and About (where useful).
- [ ] Settings contains Profiles, Memory, and General. Provider settings live inside each Profile, not as a separate global settings page.
- [ ] Provide predictable Back navigation and a way to return to Chat.
- [ ] Use responsive layouts based on available terminal width and height.
- [ ] On narrow terminals, use a single-column/page-oriented layout; on wider terminals, use available space without requiring permanent sidebars.
- [ ] All features must remain keyboard-accessible. Mouse interaction may be supported where the terminal supports it, but must not be required.
- [ ] Avoid clipped dialogs, inaccessible controls, and horizontal layouts that become unusable on small terminals.
- [ ] Preserve chat history, chat selection, and draft text when navigating between pages where practical.

### Profiles and provider configuration

- [ ] Keep exactly one active profile at a time.
- [ ] Support selecting, creating, editing, and deleting profiles with confirmation for destructive actions.
- [ ] Each profile owns its provider, endpoint, model, and model-generation parameters.
- [ ] Moving between profiles switches the complete provider configuration together.
- [ ] Provider configuration UI inside a profile includes Change Provider, Change Endpoint, Change Current Model, model discovery where supported, and model parameters.
- [ ] Model parameters include at least Temperature, Top P, Top K, Context Length, and Max Tokens where supported by the selected provider/model.
- [ ] Provider capability differences must be explicit: unsupported parameters are disabled or marked unavailable, never silently sent as if supported.
- [ ] Persist profile changes safely and atomically; retain compatibility with existing profiles.jsonl entries and provide migration/default values for new optional fields.
- [ ] Do not delete a profile's associated user files when deleting the profile unless a separate, explicit user-approved deletion flow is designed.

### Shared Instructions, Memory, and Skills

- [ ] Instructions, Memory, and Skills are shared across all profiles to avoid duplicated storage.
- [ ] These resources are selected from their original filesystem locations.
- [ ] Display the selected path and provide a clear reselect action.
- [ ] If a selected resource disappears or becomes inaccessible, show an error and ask the user to select it again.
- [ ] Do not automatically search for replacements or choose similarly named files.

#### Instructions

- [ ] Allow the user to select an instruction .jsonl file.
- [ ] Validate each non-empty line as a JSON object with the required Instruction and act fields.
- [ ] Display the file contents below the file-selection control, with useful line-level validation errors.
- [ ] The model may read valid instructions as context.
- [ ] The AI must never create, edit, rename, or delete the Instructions file.
- [ ] Only the user may change the selected file or edit its contents through an explicitly user-initiated action.

#### Memory

- [ ] Allow the user to select one shared .md Memory file.
- [ ] Display its contents below the file-selection control.
- [ ] The model may read the Memory contents as context.
- [ ] The AI may propose changes only; it must never write directly to Memory without user approval.
- [ ] Before applying a proposed change, show the exact proposed diff/content and ask the user a clear Yes/No question.
- [ ] Yes applies only the exact displayed change. No leaves the file unchanged.
- [ ] Approval is per change, not a permanent permission.
- [ ] If the file changes externally between preview and approval, detect the conflict and require a fresh preview/approval rather than overwriting unseen edits.
- [ ] Write approved changes safely (temporary file plus atomic replacement where supported) and preserve encoding/content.
- [ ] User-initiated manual editing is allowed, with an explicit action and clear indication that an external editor may open.

#### Skills

- [ ] Allow the user to select one shared Skills root folder.
- [ ] Display its real directory hierarchy and Markdown files without copying them.
- [ ] Selecting a file opens a read-only preview of its contents.
- [ ] A skill is valid only when its skill directory contains a SKILL.md main file.
- [ ] Show folders without SKILL.md as invalid/incomplete; do not make them available to the model as skills.
- [ ] Other Markdown files may provide supporting material, but SKILL.md is the required entry point.
- [ ] The model may read valid skill files as context when relevant.
- [ ] The AI must never edit, create, rename, or delete Skills files or folders.
- [ ] File and folder access errors must be visible and must not be mistaken for an empty directory.

### Persistent provider session and connection lifecycle

- [ ] Introduce a provider-session/client lifecycle instead of constructing a provider adapter for every prompt.
- [ ] Reuse the same provider adapter and reusable HTTP transport/client for requests that share the same active profile configuration.
- [ ] Use HTTP keep-alive/connection pooling where supported by the chosen transport and provider.
- [ ] Do not claim that a persistent HTTP connection is the same as provider-side conversation state. Continue sending the required conversation context according to the provider API.
- [ ] Initialize or validate the session when the active provider/profile is first used, not by blocking the TUI.
- [ ] Keep the session reusable across consecutive prompts while its configuration remains unchanged.
- [ ] Recreate/reconfigure the session when provider, endpoint, credentials, or other connection-defining settings change.
- [ ] Close transports and release resources when the application exits.
- [ ] On connection failure, show a useful status and perform bounded reconnect/retry behavior; avoid infinite retry loops.
- [ ] Distinguish Connecting, Connected/Ready, Reconnecting, and Offline/Error states.
- [ ] Do not display Connecting to provider as if a fresh connection is being made for every prompt when a reusable session is already ready.
- [ ] Keep provider calls in background workers so the TUI remains responsive.
- [ ] Ensure model-list requests and chat generation do not use the same non-thread-safe connection concurrently unless the adapter explicitly supports it.
- [ ] Third-party provider adapters must remain compatible with a documented adapter/session contract. If an adapter cannot support persistent transport, report that capability honestly and retain functional fallback behavior.

## Implementation phases

### Phase 0 — Baseline and safeguards

- [x] Record current Git branch, commit, and working-tree status before editing.
- [x] Identify and preserve all existing uncommitted user changes, especially settings.json and secrets.
- [x] Confirm client_secret.json and tokens remain excluded from Git.
- [x] Run the existing test suite and record the baseline result (31 tests passed).
- [x] Add focused tests before or alongside behavior changes.
- [x] Do not edit ROADMAP.md.

### Phase 1 — Provider session foundation

- [x] Define the provider session/transport interface and lifecycle.
- [x] Implement reusable HTTP transport for built-in Ollama and OpenAI-compatible adapters.
- [x] Preserve existing provider error handling and model discovery.
- [x] Add bounded connect retries (2 attempts), invalidate failed sessions, and close transports on exit.
- [x] Add tests proving repeated prompts reuse the same session/transport.
- [x] Add tests for endpoint isolation and cleanup.
- [x] Verify existing third-party adapter compatibility through the original Provider contract.

### Phase 2 — Profile data model and configuration

- [x] Extend profile persistence for provider/model parameters with backward-compatible defaults.
- [x] Keep provider, endpoint, model, and parameters isolated per profile.
- [x] Add validation and atomic save behavior (using the existing atomic profile writer).
- [x] Add tests for legacy profile files and parameter persistence.
- [x] Do not migrate or delete existing memory files as part of this phase.

### Phase 3 — TUI navigation and responsive layout

- [x] Replace the permanent profile/chat sidebar with the agreed popup navigation.
- [ ] Implement Chat, Settings, Profiles, and General page flows. (Chat, Settings hub, and Profile/Provider menus exist; Memory and General settings remain pending.)
- [x] Implement Back navigation through Escape on popup screens.
- [x] Move provider configuration into the selected profile's configuration page.
- [x] Implement initial responsive behavior: popup menus use terminal-relative widths; tested at 40x15 and 110x40.
- [x] Preserve existing chat operations and keyboard shortcuts; Ctrl+P now opens navigation, and Ctrl+O is the new menu shortcut (documented in README).
- [x] Add Textual interaction tests for popup, Settings/Profile/Provider navigation, Back dismissal, and narrow terminal mounting.

### Phase 4 — Shared context and file browsers

- [ ] Add shared resource configuration for Instructions, Memory, and Skills paths.
- [ ] Store references to original paths; do not copy source files.
- [ ] Implement file/folder selection with validation and missing-file recovery.
- [ ] Implement Instructions JSONL validation and read-only preview.
- [ ] Implement Memory Markdown preview and user-initiated editing.
- [ ] Implement Skills tree, SKILL.md validation, and read-only file preview.
- [ ] Add tests for valid/invalid files, missing paths, unreadable paths, and nested folders.

### Phase 5 — AI Memory approval workflow

- [ ] Define a constrained proposal format for AI-requested Memory changes.
- [ ] Show a reviewable diff before asking for approval.
- [ ] Require an explicit Yes or No for every proposed change.
- [ ] Apply only the approved diff; reject without modifying the file.
- [ ] Detect external edits between preview and approval to prevent lost updates.
- [ ] Add tests proving AI cannot write to Instructions or Skills and cannot modify Memory without approval.

### Phase 6 — Integration and platform verification

- [ ] Run the full unit and UI test suites.
- [ ] Run Python compilation and packaging checks.
- [ ] Verify on Windows.
- [ ] Verify on Linux.
- [ ] Verify on Android through Termux, including narrow terminal dimensions and keyboard navigation.
- [ ] Verify no macOS-specific requirement has been introduced; macOS remains out of scope.
- [ ] Check Git diff for accidental changes to user data, secrets, Docker configuration, and ROADMAP.md.
- [ ] Summarize completed work, tests, known limitations, and remaining tasks for user review.

## Acceptance criteria

- [ ] Sending multiple prompts in one active profile reuses its provider session/transport rather than creating a new one for every prompt.
- [ ] Switching profile switches provider configuration and uses the correct session.
- [ ] Changing connection-defining profile settings invalidates/rebuilds only the affected session.
- [ ] The popup menu is available from the main chat and does not permanently take chat width.
- [ ] The TUI remains usable at narrow Termux dimensions and wider desktop terminal dimensions.
- [ ] Back navigation works consistently.
- [ ] Instructions, Memory, and Skills are shared across profiles and remain at their original paths.
- [ ] Missing selected files/folders produce an explicit reselect flow.
- [ ] Skills without SKILL.md are visible as invalid and are not supplied to the model as usable skills.
- [ ] The AI cannot modify Instructions or Skills.
- [ ] The AI cannot modify Memory unless the user approves the exact proposed change.
- [ ] Existing chats and profiles remain readable and intact.
- [ ] Existing export/privacy behavior remains intact.
- [ ] ROADMAP.md remains byte-for-byte unchanged.
- [ ] No Git push/release occurs without the user's explicit request.

## Deferred / explicitly out of scope

- macOS support.
- Automatic upload/synchronization of user-selected context files.
- AI write access to Instructions or Skills.
- Automatic discovery or substitution of missing selected files.
- Automatic provider/server installation, model downloads, or model benchmarks.
- Changing Docker resource limits or container configuration.
- Publishing a release or pushing commits without explicit user instruction.
