#!/usr/bin/env python
"""SKINRUSH backend — Django management entry point."""
import os
import sys


def main():
    # Force our settings module even if a stale DJANGO_SETTINGS_MODULE is set
    # in the environment (e.g. left over from another project).
    os.environ["DJANGO_SETTINGS_MODULE"] = "skinrush.settings"
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django topilmadi. `pip install -r requirements.txt` ni ishga tushiring."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
