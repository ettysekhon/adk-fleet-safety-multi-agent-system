import asyncio
import os
import sqlite3
import tempfile

from google.adk.sessions import DatabaseSessionService
from google.adk.sessions.session import Event


async def test_database_persistence():
    print("Starting Database Persistence Test")
    print("==================================")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = tmp_db.name

    print(f"Temporary DB path: {db_path}")

    try:
        db_url = f"sqlite+aiosqlite:///{db_path}"
        service = DatabaseSessionService(db_url=db_url)

        print("Creating session...")
        session = await service.create_session(app_name="integration_test", user_id="tester")
        print(f"Session created: {session.id}")

        print("Appending event...")

        event = Event(
            content={"role": "user", "parts": [{"text": "integration test message"}]},
            author="tester",
        )
        await service.append_event(session, event)
        print("Event appended.")

        print("Verifying database content...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables found: {tables}")

        found_message = False
        for table_name in tables:
            table = table_name[0]
            print(f"--- Table: {table} ---")
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            for row in rows:
                print(row)

                if "integration test message" in str(row):
                    found_message = True
                    print(">>> FOUND MESSAGE IN DB! <<<")

        conn.close()

        if found_message:
            print("\nSUCCESS: Database write verified.")
        else:
            print("\nFAILURE: Message not found in database.")
            exit(1)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Removed {db_path}")


if __name__ == "__main__":
    asyncio.run(test_database_persistence())
