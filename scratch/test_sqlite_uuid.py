from sqlalchemy import text, create_engine

engine = create_engine("sqlite:///:memory:")

def test():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE test (
                id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
                val TEXT
            )
        """))
        res = conn.execute(text("INSERT INTO test (val) VALUES ('a') RETURNING *")).one()
        print(res)

if __name__ == "__main__":
    test()
