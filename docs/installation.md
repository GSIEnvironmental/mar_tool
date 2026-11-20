# Installation

## Stable release

To install mar_dss, run this command in your terminal:

```sh
uv add mar_dss
```

Or if you prefer to use `pip`:

```sh
pip install mar_dss
```

## From source

Clone the repository and install the locked dependencies with uv.

```sh
git clone https://github.com/GSIEnvironmental/mar_tool.git
cd mar_tool
uv sync --python=3.13 --locked
uv run mar_dss
```
