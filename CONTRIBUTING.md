# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs at <https://github.com/GSIEnvironmental/mar_tool/issues>.

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement" and "help wanted" is open to whoever wants to implement it.

### Write Documentation

mar_dss could always use more documentation, whether as part of the official docs, in docstrings, or even on the web in blog posts, articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at <https://github.com/GSIEnvironmental/mar_tool/issues>.

If you are proposing a feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that contributions are welcome :)

## Get Started

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/) for local development.

1. Fork the `mar_tool` repo on GitHub.

1. Clone your fork locally:

   ```sh
   git clone git@github.com:your_name_here/mar_tool.git
   cd mar_tool
   ```

1. Install the project and test tools:

   ```sh
   uv sync --python=3.13 --locked --extra test
   ```

1. Create a branch for local development:

   ```sh
   git checkout -b name-of-your-bugfix-or-feature
   ```

## Run Locally

```sh
uv run mar_dss --dev
```

Open <http://127.0.0.1:8050/>. The app reloads when you save a file.

### With Docker

Docker Compose runs the app behind Caddy at `/MAR-Tool/`.

```sh
docker compose up --build
```

Open <http://localhost:8085/MAR-Tool/>. Edits under `src/` reload automatically.

## Test and Submit

1. Run the quality checks and tests with `just qa`. Use `just testall` to test Python 3.10 through 3.13 in parallel with tox and uv.

   ```sh
   just qa
   just testall
   ```

   Test runs show branch coverage and missing lines. Run `just coverage` to also write `htmlcov/index.html`.

1. Commit your changes and push your branch to GitHub:

   ```sh
   git add .
   git commit -m "Your detailed description of your changes."
   git push origin name-of-your-bugfix-or-feature
   ```

1. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
1. Update the relevant documentation when you add functionality.
1. GitHub Actions tests pull requests to `main` on Python 3.12 and 3.13. Run `just testall` to check the full local matrix.

## Tips

To run a subset of tests:

```sh
just test tests/test_base.py
```

## Deploying

Set the Caddy request body limit to `16MB` on the server's MAR-Tool route. This allows a 10 MiB project file to fit in the encoded upload request.

Set `Referrer-Policy` to `strict-origin-when-cross-origin` on the MAR-Tool route. This lets browsers send the site origin to OpenStreetMap when loading map tiles. [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/)

Commit all changes first, including notes under "Unreleased" in [CHANGELOG.md](CHANGELOG.md). Then run:

```sh
just bump-patch   # or bump-minor / bump-major
just tag          # pushes main, then the new tag
```

The bump updates the version, dates the changelog section, commits, and tags the release. Pushing the tag triggers deployment. [GitHub Actions workflow](.github/workflows/ci-cd.yaml)

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.
