#!/usr/bin/env python3
"""
reset_password.py — Re-encrypt a user's password in the database using the
current password_salt so that login works correctly.

Run once inside the container after rebuilding:

    docker exec -it <container_name> \\
        /opt/venv/bin/python /opt/ceg/algo/api_manager/reset_password.py \\
        admin 'C@g-2O25#N0x$PRd'

Arguments:
    username     — the username to update (e.g. admin)
    new_password — the plain-text password to set (must match what you type at login)
"""
import sys
import asyncio
import os

# Ensure .alg_env is found (settings reads it from CWD)
os.chdir("/opt/ceg/algo/api_manager")
sys.path.insert(0, "/opt/ceg/algo")
sys.path.insert(0, "/opt/ceg/algo/api_manager")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    username = sys.argv[1]
    new_password = sys.argv[2]
    asyncio.run(_reset(username, new_password))


async def _reset(username: str, new_password: str):
    # Import after chdir so settings picks up the right .alg_env
    import urdhva_base.settings
    import urdhva_base.types as types
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import text

    salt = urdhva_base.settings.settings.password_salt
    print(f"[info] password_salt in use: {repr(salt)}")

    db_url = str(urdhva_base.settings.settings.db_urls["postgres_async"][0])
    safe_url = db_url.split("@")[0].split("//")[0] + "//***@" + db_url.split("@")[-1]
    print(f"[info] Connecting to: {safe_url}")

    engine = create_async_engine(
        db_url,
        pool_size=1,
        max_overflow=0,
        connect_args={"timeout": 15},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # ── Fetch current user row ────────────────────────────────────────────
        result = await session.execute(
            text(f"SELECT id, username, password FROM users WHERE lower(username) = lower(:u)"),
            {"u": username},
        )
        row = result.fetchone()
        if not row:
            print(f"[ERROR] User '{username}' not found in the 'users' table.")
            return

        user_id, db_username, stored_pw = row
        print(f"[info] Found user: id={user_id}, username={db_username!r}")
        print(f"[info] Stored password prefix: {str(stored_pw)[:30]}...")

        # ── Diagnose: try current salt ────────────────────────────────────────
        try:
            decrypted = types.Secret(str(stored_pw)).get_secret()
            print(f"[ok]   Current stored password already decrypts with salt={repr(salt)!r}")
            if decrypted == new_password:
                print(f"[ok]   Stored password already matches new_password — nothing to update.")
                return
            else:
                print(f"[warn] Stored password decrypts to a DIFFERENT value; re-encrypting.")
        except Exception as e:
            print(f"[warn] Cannot decrypt with current salt ({repr(e)}); will re-encrypt.")

        # ── Re-encrypt with current salt and update DB ────────────────────────
        # types.Secret.validate() encrypts any plain-text value with settings.password_salt
        encrypted = str(types.Secret.validate(new_password))
        print(f"[info] New encrypted value prefix: {encrypted[:30]}...")

        await session.execute(
            text("UPDATE users SET password = :pw WHERE id = :id"),
            {"pw": encrypted, "id": user_id},
        )
        await session.commit()
        print(f"\n[SUCCESS] Password for '{db_username}' has been reset.")
        print(f"          Login with: username={db_username!r}, password={new_password!r}")

    await engine.dispose()


if __name__ == "__main__":
    main()
