"""Manual debug helper for Authlib JWT decoding.

Not a unit test. Keep this file safe to import under pytest.
"""


def main() -> None:
    from authlib.jose import jwt

    # Header: {"alg":"HS256","typ":"JWT"}
    # Payload: {"sub":"1234567890","name":"John Doe","iat":1516239022}
    fake_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )

    try:
        print("Attempting decode...")
        payload = jwt.decode(fake_token, options={"verify_signature": False})
        print(f"Decoded: {payload}")
        print(f"Type: {type(payload)}")
        print(f"Sub: {payload.get('sub')}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
