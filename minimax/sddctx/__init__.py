"""sddctx - the SDD context module for the MiniMax topic.

The module wires the three required technologies together:

* **seekdb** stores and indexes the engineering material (spec entries, code
  symbols, tests) and answers the queries that build a development context.
* **MiniMax** performs the actual code modification.
* **PowerContext** persists the task state so it survives a module restart.

Public entry point: :func:`sddctx.cli.main`.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
