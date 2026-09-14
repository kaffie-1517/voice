"""One-off: create the AgentCore Memory resource Relay's phrasebook lives in.

    python scripts/create_memory.py

Needs AWS credentials with AgentCore permissions (env vars or a profile) and
AWS_REGION set to a region where AgentCore Memory is available. Prints the id
to put in AGENTCORE_MEMORY_ID.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from bedrock_agentcore.memory import MemoryClient  # noqa: E402

region = os.environ.get("AWS_REGION", "us-west-2")
client = MemoryClient(region_name=region)

print(f"Creating Relay phrasebook memory in {region} (this takes a minute or two)...")
memory = client.create_memory_and_wait(
    name="relay_phrasebook",
    description="Utterances a Relay user has chosen, for personalised prediction",
    # Raw events (exact phrasing) are kept regardless; the semantic strategy
    # additionally extracts records that can be retrieved by meaning.
    strategies=[
        {
            "semanticMemoryStrategy": {
                "name": "phrasebook",
                "namespaces": ["/relay/{actorId}/phrasebook"],
            }
        }
    ],
    event_expiry_days=365,
)

memory_id = memory["id"]
print(f"\nDone. Add this to server/.env:\n\n  AGENTCORE_MEMORY_ID={memory_id}\n")
sys.exit(0)
