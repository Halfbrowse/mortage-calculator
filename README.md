# Mortgage Calculator

A command-line mortgage calculator built with Python and uv.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Setup

```bash
uv sync
```

## Usage

```bash
uv run main.py
```

## Development

Install dev dependencies and pre-commit hooks:

```bash
uv sync
uv run pre-commit install
```

Run linting and formatting:

```bash
uv run ruff check .
uv run ruff format .
```
