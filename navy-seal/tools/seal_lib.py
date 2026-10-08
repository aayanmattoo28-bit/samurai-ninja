"""Bridge to the shared procedural-modelling library (../../tools/kage_lib.py).

The Navy SEAL build reuses the mesh builders (MD, grid, limb, sweep, tube, lathe ...), the node-material
helper (NB) and the generic materials from the samurai project, but keeps its own textures in
navy-seal/textures.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEAL_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(SEAL_ROOT)
SHARED = os.path.join(REPO_ROOT, "tools")
if SHARED not in sys.path:
    sys.path.insert(0, SHARED)

import kage_lib  # noqa: E402
from kage_lib import *  # noqa: E402,F401,F403
from kage_lib import (_ao, _bevel, _hard_edges, _triplanar, _updust, _COLLS, _IMAGES, _MATS,  # noqa: E402,F401
                      _WRINKLE_SPACE, _WRINKLE_TEX)

TEX_DIR = os.path.join(SEAL_ROOT, "textures")
kage_lib.TEX_DIR = TEX_DIR


def deg(a):
    import math
    return math.radians(a)


def reset_state():
    for d in (_COLLS, _IMAGES, _MATS, _WRINKLE_TEX, _WRINKLE_SPACE):
        d.clear()
