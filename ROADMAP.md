# cavde.connect Roadmap

> This roadmap is the agreed project plan. Do not modify this file after user approval unless the user explicitly authorizes the change.

## Project principles

- Universal AI client; not restricted to CAVDE.
- Python is the host application language.
- Provider adapters may use any programming language and suitable communication mechanism.
- Runtime availability matters more than a fixed OS or language-version matrix.
- Windows is the first development target; Linux and macOS are later targets.
- Textual provides the keyboard-driven terminal interface.
- Exactly one profile is active at a time.
- Profiles share the chat collection; memory remains separate per profile.
- The profile database filename must be exactly `profiles.jsonl`.
- Conversation files use JSONL input/output pairs and remain easy to review manually.
- Dataset export is opt-in, disabled by default, manually initiated, and user-selected.
- Privacy and low resource usage are core requirements.
- Do not bundle built-in AI skills or a skills.md system.

## Phase 0 — Foundation

- [x] Create project directory at `D:\cavde.connect`.
- [x] Establish Python package layout.
- [x] Add project metadata and dependency declaration.
- [x] Add required `profiles.jsonl` with a default profile.
- [x] Add shared chat and per-profile memory directories.
- [x] Add profile JSONL load/save implementation.
- [x] Add CAVDE-compatible chat JSONL storage.
- [x] Reserve chat name `profiles`.
- [x] Add provider adapter base contract.
- [x] Add initial Ollama HTTP adapter.
- [x] Add Textual application shell.
- [x] Add README and Git ignore rules.
- [x] Initialize Git repository.
- [x] Run Python compilation checks and storage unit tests.

## Phase 1 — Core usability

- [x] Complete profile selection and profile management UI.
- [x] Complete chat create, select, rename, delete, save, and load flows.
- [x] Add chat title and safe filename handling.
- [x] Improve message rendering and scrolling.
- [x] Add provider/model/endpoint editing.
- [x] Add memory editor or safe external-editor integration.
- [x] Add friendly errors and connection status.

## Phase 2 — Provider compatibility

- [x] Add llama.cpp server adapter.
- [x] Add OpenAI-compatible endpoint adapter.
- [x] Define practical adapter integration guidance without enforcing one transport.
- [x] Support external adapter processes/libraries where useful.
- [x] Add provider capability checks and model listing where supported.

## Phase 3 — Privacy-preserving dataset export

- [x] Design explicit user selection of chats and folders.
- [x] Keep export disabled by default.
- [x] Require explicit manual export action.
- [x] Never automatically upload or transmit exported data.
- [x] Design archive anonymization for both paths and sensitive content.
- [x] Design collision-resistant pseudonymous names using random identifiers and salted hashes.
- [x] Package selected export into `.tar.xz`.
- [x] Add preview/review step before creating the archive.
- [x] Test that unselected content is never included.

## Phase 4 — Portability and polish

- [x] Verify supported Windows environments based on available Python runtime.
- [x] Add Linux compatibility.
- [x] Defer macOS compatibility implementation to Apple-platform developers.
- [x] Add packaging and launch conveniences.
- [x] Add broader tests and documentation.

## Resource constraints

- Do not run model servers, model downloads, benchmarks, broad disk scans, or heavyweight builds by default.
- Install additional compilers/runtimes only when a concrete feature needs them.
- Prefer standard-library implementations and small dependencies.
- Keep background work bounded and user-visible.
