# Justfile for mar_dss
# Usage:   just <recipe>      Run `just` with no args to list all recipes.

set quiet

# List available recipes
[private]
default:
    just --list --unsorted

# -- quality ------------------------------------------------------------------

# Run all the formatting, linting, and testing commands
[group: 'quality']
qa:
    uv run pre-commit run --all-files
    # uv run --python=3.13 --extra test ty check .
    uv run --python=3.13 --extra test pytest .

# Run all the tests, but allow for arguments to be passed
[group: 'quality']
test *ARGS:
    echo "Running with arg: {{ARGS}}"
    uv run --python=3.13 --extra test pytest {{ARGS}}

# Run all the tests for all the supported Python versions
[group: 'quality']
testall:
    uv run --python=3.10 --extra test pytest
    uv run --python=3.11 --extra test pytest
    uv run --python=3.12 --extra test pytest
    uv run --python=3.13 --extra test pytest

# Run all the tests, but on failure, drop into the debugger
[group: 'quality']
pdb *ARGS:
    echo "Running with arg: {{ARGS}}"
    uv run --python=3.13  --extra test pytest --pdb --maxfail=10 --pdbcls=IPython.terminal.debugger:TerminalPdb {{ARGS}}

# Run coverage, and build to HTML
[group: 'quality']
coverage:
    uv run --python=3.13 --extra test coverage run -m pytest .
    uv run --python=3.13 --extra test coverage report -m
    uv run --python=3.13 --extra test coverage html

# -- build --------------------------------------------------------------------

# Build the project, useful for checking that packaging is correct
[group: 'build']
build:
    rm -rf build
    rm -rf dist
    uv build

# -- versioning ---------------------------------------------------------------

# Show what each bump level (patch / minor / major) would produce
[group: 'versioning']
bump:
    uv run --extra test bump-my-version show-bump

# Bump patch version (e.g. 1.2.3 to 1.2.4)
[group: 'versioning']
bump-patch:
    uv run --extra test bump-my-version bump patch

# Bump minor version (e.g. 1.2.3 to 1.3.0)
[group: 'versioning']
bump-minor:
    uv run --extra test bump-my-version bump minor

# Bump major version (e.g. 1.2.3 to 2.0.0)
[group: 'versioning']
bump-major:
    uv run --extra test bump-my-version bump major

# Push main and the tag from the last bump. Pushing the tag deploys to production.
[group: 'versioning']
tag:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$(uv run --extra test bump-my-version show current_version)
    git rev-parse --verify --quiet "refs/tags/v${version}" >/dev/null \
        || { echo "No tag v${version}. Run just bump-patch (or -minor/-major) first."; exit 1; }
    git push origin main
    git push origin "v${version}"

# -- cleanup ------------------------------------------------------------------

# remove all build, test, coverage and Python artifacts
[group: 'cleanup']
clean: clean-build clean-pyc clean-test

# remove build artifacts
[group: 'cleanup']
clean-build:
    rm -fr build/
    rm -fr dist/
    rm -fr .eggs/
    find . -name '*.egg-info' -exec rm -fr {} +
    find . -name '*.egg' -exec rm -f {} +

# remove Python file artifacts
[group: 'cleanup']
clean-pyc:
    find . -name '*.pyc' -exec rm -f {} +
    find . -name '*.pyo' -exec rm -f {} +
    find . -name '*~' -exec rm -f {} +
    find . -name '__pycache__' -exec rm -fr {} +

# remove test and coverage artifacts
[group: 'cleanup']
clean-test:
    rm -f .coverage
    rm -fr htmlcov/
    rm -fr .pytest_cache
