# <img src="https://github.com/BrandtBoys/DocTide/blob/main/docs/DocTide_logo-min.png?raw=true" width="70" style="vertical-align: middle"/> DocTide Action

DocTide brings LLM-powered, function-level documentation directly to your GitHub Pull Requests — seamlessly, automatically, and at the speed of development.

Let your code explain itself!

## What It Does
- Scans committed changes

- Auto-generates function-level comments using a Large Language Model (LLM)

- Opens a Pull Request with suggested docstring improvements

## Inputs

### `testing`

**Optional** Boolean. If true, DocTide will run in `testing` mode. Defaults to false.

## Outputs

A Pull Request containing suggested function-level comments for all modified functions.

## Example usage

```yml
jobs:
  DocTide_job:
    runs-on: ubuntu-latest
    name: Run Doctide
    steps:
      - name: Checkout
        uses: actions/checkout@v3
        with:
            fetch-depth: 0
      - name: run DocTide action
        id: doctide
        uses: BrandtBoys/Bachelor@v20
        with:
          testing: false
```
