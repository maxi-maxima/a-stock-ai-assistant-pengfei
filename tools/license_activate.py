import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.license import activate_from_code, get_machine_id


def main():
    parser = argparse.ArgumentParser(description="Activate license using an offline code")
    parser.add_argument("--code", default="", help="Activation code")
    parser.add_argument("--show-machine-id", action="store_true", help="Only show machine id")
    args = parser.parse_args()

    machine_id = get_machine_id()
    if args.show_machine_id:
        print(machine_id)
        return

    code = args.code.strip()
    if not code:
        try:
            code = input("Activation code: ").strip()
        except EOFError:
            code = ""

    if not code:
        print("ERROR: activation code is required")
        sys.exit(1)

    ok, msg = activate_from_code(code, expected_machine_id=machine_id)
    if ok:
        print("OK: license activated")
        sys.exit(0)
    print("ERROR:", msg)
    sys.exit(2)


if __name__ == "__main__":
    main()
