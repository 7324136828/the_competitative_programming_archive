merging-project-skill
Merge project 1 from the root folder and project 2 from the repo folder to create a unified project with combined functionality and user-specified features. Use when asked to merge two codebases or projects into a single integrated project.

Instructions
Merging Project Skill
A skill for combining two distinct projects/codebases (Project 1 in the root folder, Project 2 in the repo folder) into a unified codebase that incorporates the full functionality of both, plus any additional features specified in a user prompt.

When to Use
When combining a project located in the root directory with another project located in a repo folder.
When you need to integrate two codebases while adhering to custom user specifications and merging rules.
Step-by-Step Workflow
Analyze Codebases:

Inspect Project 1 in the root folder to understand its structure, dependencies, configuration files, and core APIs.
Inspect Project 2 in the repo folder to understand its structure, dependencies, and integration points.
Resolve Dependency and Structure Conflicts:

Merge configuration files (e.g., package.json, requirements.txt, Cargo.toml, pyproject.toml, or Dockerfiles) to ensure both projects' dependencies are satisfied without version conflicts.
Design a unified directory layout that accommodates both codebases (e.g., placing Project 2 under a dedicated module path or merging overlapping modules cleanly).
Integrate Functionality:

Port or integrate core modules from Project 2 into the root project structure, adjusting import paths, namespaces, and configuration bindings.
Ensure full functionality of Project 1 and Project 2 remains intact and operational.
Incorporate User Specifications:

Apply any additional feature requirements, wiring logic, or custom endpoints provided in the user's specification prompt.
Validate and Test:

Write or update build/test scripts to verify that the merged project compiles successfully and passes functional tests.
Provide clear setup, build, and run instructions for the user.