#!/usr/bin/env python3
"""
====================================================
STORYVAULT v0.1 - Storyworld Operating System
====================================================
Local-first, markdown-native creative OS.
Powered by OpenAI gpt-4o-mini.
====================================================
"""

import sys
import os

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import CLI
from src.commands import CommandRouter


def main():
    cli = CLI()
    router = CommandRouter(cli)

    if len(sys.argv) < 2:
        cli.show_main_menu()
        return

    command = sys.argv[1]
    args = sys.argv[2:]

    try:
        router.route(command, args)
    except KeyboardInterrupt:
        cli.line()
        cli.msg("  OPERATION CANCELLED")
        cli.line()
    except Exception as e:
        cli.error(f"Fatal: {e}")
        raise


if __name__ == "__main__":
    main()
