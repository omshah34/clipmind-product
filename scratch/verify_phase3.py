import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.discovery import get_discovery_service
from services.visual_engine import VisualEngine

async def verify_discovery():
    print("--- Verifying AI Semantic Discovery ---")
    discovery = get_discovery_service()
    
    mock_transcript = {
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "I think artificial intelligence is going to change the world."},
            {"start": 6.0, "end": 12.0, "text": "If you want to build a successful startup, you need to focus on growth."},
            {"start": 13.0, "end": 20.0, "text": "The price of Bitcoin is going up today."}
        ]
    }
    
    # 1. Indexing
    print("Indexing mock transcript...")
    await discovery.add_job_to_index("job_verify_99", mock_transcript)
    
    # 2. Search
    queries = ["How can I build a business?", "What is the future of technology?"]
    for q in queries:
        print(f"Searching for: '{q}'")
        results = await discovery.search_clips(q, limit=1)
        if results:
            print(f"Top result: [{results[0]['score']:.2f}] {results[0]['text']}")
        else:
            print("No results found.")
    print()

async def verify_broll():
    print("--- Verifying B-Roll Pulse ---")
    keywords = ["startup", "money", "growth"]
    print(f"Searching B-roll for: {keywords}")
    clips = await VisualEngine.find_contextual_broll(keywords)
    for c in clips:
        print(f"Found Clip: {c['preview']} -> {c['url'][:30]}...")
    print()

async def main():
    try:
        await verify_discovery()
        await verify_broll()
        print("Verification Complete.")
    except Exception as e:
        print(f"Verification Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
