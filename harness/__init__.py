"""The persona harness: a small MCP client, three postures, and the evidence.

Not part of the deployed service. The `Dockerfile` copies only `star/`,
`research_dept/`, and `web/`, and `.gcloudignore` lists `harness/` so the source
upload does not carry it either. It is also absent from `pyproject.toml`'s
explicit `[tool.setuptools] packages` list, which is the third and quietest of
those three: a package not named there is not installed, so nothing in the
deployed image can import this directory even by accident.
"""
