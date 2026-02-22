import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.license import build_payload, encode_license, get_machine_id, sign_payload


def main():
    parser = argparse.ArgumentParser(description="Generate offline license activation code")
    parser.add_argument("--user", default="", help="User name or label")
    parser.add_argument("--days", type=int, default=30, help="License duration in days")
    parser.add_argument("--machine-id", default="", help="Target machine id")
    parser.add_argument("--out", default="", help="Optional output file to write activation code")
    args = parser.parse_args()

    if args.days <= 0:
        print("ERROR: days must be a positive integer.")
        sys.exit(1)

    machine_id = args.machine_id.strip() or get_machine_id()
    payload = build_payload(args.user, args.days, machine_id=machine_id)
    sig = sign_payload(payload)
    code = encode_license(payload, sig)

    print("Machine ID:", machine_id)
    print("Activation Code:")
    print(code)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(code)
        print("Saved to:", args.out)


if __name__ == "__main__":
    main()
