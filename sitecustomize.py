import torch

def _persona_identity_compile(fn=None, *args, **kwargs):
    if fn is None:
        def _decorator(f):
            return f
        return _decorator
    return fn

torch.compile = _persona_identity_compile
