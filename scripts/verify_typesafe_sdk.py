"""Pin API surface của typesafe-sdk trước khi viết JevClient.

Chạy: uv run python scripts/verify_typesafe_sdk.py
Nếu TYPESAFE_API_KEY có trong env sẽ ping live 1 câu noul.
"""
import inspect
import os
import sys


def main() -> int:
    try:
        import typesafe_sdk
    except ImportError:
        print("FAIL: khong import duoc module 'typesafe_sdk' — kiem tra pip install typesafe-sdk")
        return 1
    names = [n for n in dir(typesafe_sdk) if not n.startswith("_")]
    print("typesafe_sdk exports:", names)
    from typesafe_sdk import TypeSafeClient
    print("TypeSafeClient methods:", [n for n in dir(TypeSafeClient) if not n.startswith("_")])
    for m in ("system_one", "systemOne", "judge"):
        if hasattr(TypeSafeClient, m):
            print(f"signature {m}:", inspect.signature(getattr(TypeSafeClient, m)))
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("(khong co TYPESAFE_API_KEY — skip live ping)")
        return 0
    from typesafe_sdk import Noul
    client = TypeSafeClient()
    resp = client.system_one(
        state="The login button says 'Sign in'.",
        questions={"ok": Noul(instructions="Does the text mention a sign-in button?")},
    )
    print("live ping answers:", resp.answers if hasattr(resp, "answers") else resp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
