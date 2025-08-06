# AGENTS.md

## Coding Conventions
- Use **Python 3.10**.
- Follow **PEP 8** style with a maximum line length of **80 characters**.
- Format all Python code with **Black**.
- Include docstrings for all public modules, classes, and functions.
- Use type hints where practical.

## Testing and Validation
- Before committing, run:
  - `pre-commit run --files <modified files>`
  - `pytest`
- If only documentation is changed, run `pytest --collect-only`.
- Fix any failing tests or lint errors before submitting.

## Pull Request Guidelines
- In the PR description, provide:
  - A concise summary of the changes.
  - Output or logs from the above testing commands.
- Ensure the working directory is clean (`git status` shows no changes) before final commit.
