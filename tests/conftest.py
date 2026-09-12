import builtins
from gp_store import AppError

# Test-only compatibility for regression cases that reference AppError directly.
builtins.AppError = AppError
