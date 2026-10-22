"""Template package for a new Sahayak module.

Copy this directory to create a new module.  Rename the folder, update
the ``name`` property, register your tools in ``register_tools``, and
add the name to ``ENABLED_MODULES``.
"""

from sahayak.modules._template.module import module

__all__ = ["module"]
