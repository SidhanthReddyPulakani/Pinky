import sqlite3

c = sqlite3.connect("pinky.db")

print("TABLES:")
print(
    c.execute(
        """
        SELECT name, type
        FROM sqlite_master
        WHERE type IN ('table', 'index')
        ORDER BY type, name
        """
    ).fetchall()
)

print("\nOUTBOX FKs:")
print(c.execute("PRAGMA foreign_key_list(outbox)").fetchall())

print("\nEVENT COLUMNS:")
print(c.execute("PRAGMA table_info(events)").fetchall())

print("\nOUTBOX COLUMNS:")
print(c.execute("PRAGMA table_info(outbox)").fetchall())