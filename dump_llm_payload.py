"""Dump what gets sent to LLM for analysis.

Run this to see the actual JSON payload that goes to the model.
"""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.llm.batch import BatchAnalyzer, BATCH_SYSTEM_PROMPT
from pipeline.llm.client import get_client

# Sample some calls to see what we're sending
SAMPLE_CALLS = [
    {
        "id": "c_00001",
        "turns": [
            {"role": "bot", "text": "Здравствуйте! Меня зовут Александр, я позвонил вам"},
            {"role": "client", "text": "Алло?"},
            {"role": "bot", "text": "Да, это я, компания Ботамин"},
            {"role": "client", "text": "Не нужно, bye"},
        ],
        "duration_sec": 12.5
    },
    {
        "id": "c_00002",
        "turns": [
            {"role": "bot", "text": "Здравствуйте!"},
            {"role": "client", "text": ""},
        ],
        "duration_sec": 3.0
    },
]

def main():
    print("=" * 80)
    print("LLM PAYLOAD ANALYSIS")
    print("=" * 80)

    client = get_client()
    analyzer = BatchAnalyzer(client, batch_size=180)

    # Pack sample calls
    packed = analyzer.pack_calls(SAMPLE_CALLS)

    print("\n1. SYSTEM PROMPT:")
    print("-" * 80)
    print(BATCH_SYSTEM_PROMPT[:500] + "..." if len(BATCH_SYSTEM_PROMPT) > 500 else BATCH_SYSTEM_PROMPT)

    print("\n2. PACKED PAYLOAD:")
    print("-" * 80)
    print(packed[:1000] + "..." if len(packed) > 1000 else packed)

    print("\n3. STATS:")
    print("-" * 80)
    data = json.loads(packed)
    total_turns = sum(len(c["t"]) for c in data["calls"])
    total_chars = sum(len(str(c)) for c in data["calls"])

    print(f"Calls: {len(data['calls'])}")
    print(f"Total turns: {total_turns}")
    print(f"Payload size: {len(packed)} chars (~{len(packed)//4} tokens)")

    print("\n4. PER-CALL BREAKDOWN:")
    for call in data["calls"]:
        turns_by_role = {"b": 0, "c": 0}
        for t in call["t"]:
            turns_by_role[t["r"]] += 1
        print(f"  {call['i']}: {len(call['t'])} turns (bot={turns_by_role['b']}, client={turns_by_role['c']})")

    print("\n5. REAL DATA SAMPLE:")
    print("-" * 80)
    print("Let's check what a REAL batch looks like from actual pipeline...")

    # Try to load some real data
    try:
        from pipeline.ingest import ingest
        from pipeline.profile import profile_data

        # This would need actual data source
        print("\nTo see real data, run:")
        print("  python -m pipeline --file data/raw.csv --llm-scope focus --dry-run")

    except Exception as e:
        print(f"Couldn't load real data: {e}")

if __name__ == "__main__":
    main()
