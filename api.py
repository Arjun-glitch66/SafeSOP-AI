"""Compatibility shim. The API lives in the app/ package; this keeps `uvicorn api:app` and
`import api` working.

`api.NAME` reads, and assignments to it (including pytest's monkeypatch), are forwarded to the
app module that defines NAME, so `monkeypatch.setattr(api, "DB_PATH", ...)` changes the setting
the code actually uses.
"""
import sys
import types

from app import audit, auth, config, db, limits, main, schemas, storage
from app.routers import documents, health, requests, reviews, versions
from app.routers import auth as auth_router
from app.services import evaluation, generation, jobs, pdf

# Search order. Each name the tests touch is defined in exactly one of these modules.
_MODULES = (config, db, schemas, storage, audit, auth, limits, generation, jobs, evaluation, pdf,
            documents, requests, versions, reviews, health, auth_router, main)


def _owner(name):
    for module in _MODULES:
        if name in vars(module):
            return module
    return None


_saved = {}  # forwarded name -> stack of the values each assignment through api replaced


class _Shim(types.ModuleType):
    def __getattr__(self, name):
        owner = _owner(name)
        if owner is None:
            raise AttributeError(f"module 'api' has no attribute '{name}'")
        return getattr(owner, name)

    def __setattr__(self, name, value):
        owner = _owner(name)
        if owner is None:
            super().__setattr__(name, value)
        else:
            _saved.setdefault(name, []).append(getattr(owner, name))
            setattr(owner, name, value)

    def __delattr__(self, name):
        # monkeypatch.undo() deletes what it set on `api` (newest first): restore the value
        # that assignment replaced.
        if _saved.get(name):
            setattr(_owner(name), name, _saved[name].pop())
        else:
            super().__delattr__(name)


sys.modules[__name__].__class__ = _Shim
