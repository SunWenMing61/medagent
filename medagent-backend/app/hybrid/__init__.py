"""Hybrid execution package.

Import concrete components from their modules.  Keeping package initialization
side-effect free avoids a cycle when the controlled graph imports task helpers.
"""
