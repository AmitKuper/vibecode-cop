# Code Quality Rules

## 1. Code Organization & File Size

Scripts/code files must not exceed **150 lines**. Refactor as follows:
- Extract helper functions into separate modules
- Apply single responsibility principle per class (use mixins for shared behavior)
- Split large files 50/50 (e.g., Input handling + Output handling in separate files)
- Extract magic numbers and constants to `constants.py`
- Move reusable logic to separate utility modules

## 2. Comments & Documentation

- **Code comments**: Explain *why*, not *what*; only where the logic isn't self-evident
- **Docstrings**: Every method, class, and function must have detailed docstrings
- **Naming**: Use descriptive, theory-grounded names for classes, parameters, and methods

## 3. Testing & Test Documentation

- Every module must include a test module/document alongside implementation
- Document test scenarios, edge cases, and validation test plans
- Maintain clear test naming and organization (unit/, integration/ folders)

## 4. Code Reuse & Design

- No code duplication; implement each feature once with single responsibility
- Follow OOP principles; use inheritance and mixins for shared functionality
- Avoid copy-paste development

## 5. Testing & Quality

- Create unit tests for each method and class
- Target test coverage ≥ 85%
- Document edge cases and error handling scenarios
- Zero Ruff violations

## 6. Configuration & Security

- **Configurable parameters** → store in config files (JSON or YAML)
- **Secrets, API keys, passwords** → environment variables only, never committed to code
- Use `.env.example` as a template for required variables
- Ensure `.gitignore` excludes `.env` and sensitive files

## 7. Git Workflow

- Write clear, descriptive commit messages:
  - `Feature: <feature_name>` for new features
  - `BugFix: <issue_description>` for bug fixes
  - `Refactor: <scope>` for refactoring
  - `Docs: <change>` for documentation
- Keep commits atomic and focused on a single logical change
- `hw6-common/` was imported from a separate shared repository via `git subtree` and is no
  longer a submodule — it is tracked and edited directly in this repo. Never push to the
  old `agent-orchestration-course-t6-common` repository from here.

## 8. Token Usage Cost Tracking

- **Record token usage for every step, phase, or TODO item** in `docs/cost.md`
- Use actual token counts from API responses when available; otherwise estimate
- Format: `Tokens: ~X input / ~Y output` (or `Tokens: ~X total` if breakdown unavailable)
- Include cumulative totals per phase so overall cost is trackable

## 9. Progress Tracking & TODO Maintenance

- **Update `docs/TODO.md` after every progress**: do not let it drift from reality
- When a task or phase is completed:
  - Mark checklist items with `[x]`
  - Update phase status to `✅ Complete` with the commit hash
  - Add brief outcome notes if relevant (test count, coverage, deviations)
- When a task is started but not finished, mark it `🚧 In Progress`
- When scope changes mid-phase, update the task description rather than silently diverging
- TODO.md updates should be in the same commit as the work they describe

## 10. Package & Dependency Management

- **Use `uv`** (not pip, not poetry) for all package management — `uv add`, `uv run`, `uv sync`
- Commit `uv.lock` alongside `pyproject.toml`
- **Semantic versioning** must be kept in sync across: `src/<package>/shared/version.py`,
  `pyproject.toml`, and `config/rate_limits.json`
- `pyproject.toml` is the single source of build metadata, Ruff config, and pytest config
- Never use `requirements.txt`

## 11. Architecture Patterns

- **SDK layer** (`src/<package>/sdk/sdk.py`): all business logic exposed through a single
  SDK entry point. CLI and external callers must go through SDK — never call services/agents
  directly.
- **API Gatekeeper** (`src/<package>/shared/gatekeeper.py`): all LLM API calls go through
  the Gatekeeper (rate limiting from `config/rate_limits.json`, retries, logging). No agent
  calls the LLM API directly.
- **OOP design**: use inheritance and mixins for shared agent and reviewer behaviour.
- **Thread safety**: any component running reviewers or agents in parallel must use locks
  or queues for shared state.
- **Extension points**: each major component must expose a hook or registration mechanism
  so new agents/reviewers can be added without modifying core orchestration code.

## 12. Mandatory Deliverables

- **`README.md`** at project root — must include installation, quick-start, usage,
  configuration, module reference, troubleshooting, and project structure sections
- **`docs/PRD_<component>.md`** — one component-level PRD per major subsystem
- **`notebooks/`** — at least one Jupyter notebook with cost analysis and sensitivity analysis
- **`assets/`** — architecture diagrams, sample output screenshots
- **`config/rate_limits.json`** — externalized LLM rate limit configuration
- **`config/setup.json`** — externalized application setup (paths, log levels)
- **`docs/cost.md`** — token usage tracking per phase
- **`docs/TODO.md`** — kept current; update in same commit as work
