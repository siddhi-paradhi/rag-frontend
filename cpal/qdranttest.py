from dotenv import load_dotenv
load_dotenv()

import os
from qdrant_client import QdrantClient

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

res = client.scroll(
    collection_name=os.getenv("QDRANT_COLLECTION_NAME", "WEB_DATA"),
    limit=3,
    with_payload=True
)

for pt in res[0]:
    print(f"ID: {pt.id}")
    print("Payload:", pt.payload)
    print("-" * 40)



