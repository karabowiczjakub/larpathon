# Coding instructions

- Keep responses concise and implementation-focused.
- Prefer minimal changes over large refactors.
- Change only files necessary for the requested task.
- Avoid unnecessary abstractions.
- Avoid verbose comments and docstrings unless they add real value.
- Prefer simple, readable Python over clever code.
- Do not rewrite working code without a clear reason.
- Preserve the existing project structure and naming conventions.
- When fixing a bug, make the smallest safe fix.
- When adding a feature, keep the diff small.
- Do not add dependencies unless necessary.
- Do not modify unrelated files.
- Before editing, briefly inspect the relevant files.
- After editing, summarize:
  1. what changed,
  2. which files changed,
  3. how to test it.

## Python

- Follow PEP 8.
- Prefer type hints for non-trivial functions.
- Avoid deeply nested logic.
- Prefer small functions with clear responsibility.
- Use existing dependencies before adding new ones.

## Git

- Never commit or push unless explicitly asked.
- Never modify `main` directly unless explicitly asked.
- Assume development happens on the current branch.

## Hackathon mode

- Prioritize working functionality over perfect architecture.
- Prefer solutions that can be implemented and tested quickly.
- Avoid premature optimization.
- Avoid building infrastructure that is not needed for the demo.
- If there are multiple valid approaches, choose the simplest one that works.

## Architecture and modularity

- Design the project for parallel development by multiple developers.
- Prefer modular architecture with clearly separated responsibilities.
- Keep modules loosely coupled and highly cohesive.
- Avoid putting business logic directly in `app.py`.
- Treat `app.py` mainly as the application entry point and UI orchestration layer.
- Separate UI, domain logic, data access, integrations, routing, configuration, and utilities.
- Prefer dependency injection over hard-coded dependencies.
- Depend on abstractions where it improves testability and replaceability.
- Avoid circular dependencies.
- Keep public module interfaces small and explicit.
- Prefer composition over inheritance.
- Avoid global mutable state.
- Keep side effects at system boundaries.

## Design patterns

Use design patterns only where they reduce coupling or make parallel development easier.

Preferred patterns when appropriate:

- Strategy Pattern:
  for interchangeable algorithms, scoring functions, routing strategies, optimization methods, or providers.

- Factory Pattern:
  for constructing interchangeable services, clients, data providers, or algorithm implementations.

- Adapter Pattern:
  for wrapping external APIs, libraries, databases, GIS services, weather services, or other third-party systems behind stable internal interfaces.

- Repository Pattern:
  for isolating data access from business logic.

- Service Layer:
  for application/business logic shared between UI components or endpoints.

- Facade Pattern:
  for exposing a simple interface over complex subsystems.

- Observer / Event-based approach:
  only when components genuinely benefit from being decoupled through events.

- Dependency Injection:
  prefer passing dependencies explicitly instead of importing and instantiating them everywhere.

Do not introduce patterns just for the sake of using patterns.
Prefer simple interfaces and composition when a full pattern would add unnecessary complexity.

## Team development

- Structure the code so developers can work on separate modules with minimal file overlap.
- Avoid large central files that many developers need to edit.
- Prefer one responsibility per module.
- New features should usually be added by extending a module or implementing an interface, rather than modifying many unrelated files.
- Keep shared contracts stable.
- When creating a new subsystem, define its interface before implementation when practical.
- Avoid hidden coupling between modules.
- Minimize changes to shared files such as `app.py`, central configuration, and package initializers.
- Prefer feature-oriented or domain-oriented modules over dumping unrelated helpers into `utils.py`.
- Do not create generic utility modules unless the functionality is genuinely shared.

