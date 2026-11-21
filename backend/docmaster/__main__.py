"""Entry point: `python -m docmaster --templates-dir … --output-dir …` or the PyInstaller sidecar."""
from __future__ import annotations
import argparse, logging, os, sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="docmaster-backend")
    ap.add_argument("--templates-dir", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path, help="default output folder (overridden by the saved setting)")
    ap.add_argument("--data-dir", type=Path, default=None, help="where settings.json lives")
    ap.add_argument("--user-templates-dir", type=Path, default=None, help="user-added templates (default: <output-dir>/templates)")
    ap.add_argument("--soffice", default=os.environ.get("DOCMASTER_SOFFICE"))
    ap.add_argument("--log-level", default=os.environ.get("DOCMASTER_LOG_LEVEL", "INFO"))
    args = ap.parse_args(argv)
    from .logging_ import configure
    configure(args.log_level, args.data_dir.resolve() if args.data_dir else None)
    from .storage.cleanup import sweep_temp
    logging.getLogger("docmaster").info("startup cleanup: %s", sweep_temp())
    # stdout is the protocol channel: force utf-8 and line buffering regardless of console settings
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stdin.reconfigure(encoding="utf-8")
    from .rpc.methods import build_methods
    from .rpc.server import Server
    Server(build_methods(args.templates_dir.resolve(), args.output_dir.resolve(), args.soffice, args.data_dir.resolve() if args.data_dir else None,
                               user_templates_dir=args.user_templates_dir.resolve() if args.user_templates_dir else None)).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
