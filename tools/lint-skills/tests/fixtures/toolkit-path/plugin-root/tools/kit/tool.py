#!/usr/bin/env python3
"""Fixture tool: finds its toolkit from its own file, never a home path."""
import os

# A comment may name ~/.claude/skills and ~/.claude/agents.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
