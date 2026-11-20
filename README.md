# MAR-Tool

Managed Aquifer Recharge Decision Support System: a web app for checking whether a managed aquifer recharge project is feasible.

It runs at <https://apps.gsienv.com/MAR-Tool/>.

## Run it locally

You need [uv](https://docs.astral.sh/uv/).

```sh
uv run mar_dss --dev
```

Then open <http://127.0.0.1:8050/>. The app reloads when you save a file.

### With Docker

This runs the app the same way as the server, behind Caddy at `/MAR-Tool/`.

```sh
docker compose up --build
```

Then open <http://localhost:8085/MAR-Tool/>. Edits under `src/` reload too.

## Tests

```sh
just test
```

## Releases

`just bump-patch` (or `bump-minor` / `bump-major`), then `just tag`. Pushing
the tag deploys to the server. See [CONTRIBUTING.md](CONTRIBUTING.md).
