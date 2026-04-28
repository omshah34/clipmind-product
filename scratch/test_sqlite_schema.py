from sqlalchemy import text, create_engine

engine = create_engine("sqlite:///clipmind_dev.db")

def test():
    with engine.begin() as conn:
        res = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'")).fetchone()
        print("Schema:", res[0] if res else "Not found")

if __name__ == "__main__":
    test()
