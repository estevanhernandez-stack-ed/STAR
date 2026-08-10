# Explicit re-export: `adk web` discovers the root agent by importing this
# package, so the submodule import is the point, not an accident. The
# redundant alias is what tells a linter that.
from . import agent as agent
