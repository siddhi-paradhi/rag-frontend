from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams


def upload_to_qdrant(docs, embeddings, collection_name="cpal_data"):
    url = "http://localhost:6333"
    client = QdrantClient(url=url)

    if client.collection_exists(collection_name=collection_name):
        print(f"Deleting existing collection: {collection_name}")
        client.delete_collection(collection_name=collection_name)

    print(f"Creating collection: {collection_name}")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )

    qdrant = Qdrant.from_documents(
        documents=docs,
        embedding=embeddings,
        location=url,
        collection_name=collection_name,
    )

    print(f"Uploaded {len(docs)} chunks to Qdrant at {url}")
    return qdrant


if __name__ == "__main__":
    from loader import load_docs
    from chunker import chunk_docs
    from embedder import get_embeddings

    print("Loading documents...")
    docs = load_docs("data")

    print("Chunking documents...")
    chunks = chunk_docs(docs)

    with open("extracted_chunks.txt", "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(f"\n--- Chunk #{i+1} ---\n")
            f.write(chunk.page_content + "\n")

    print("Exported all chunks to extracted_chunks.txt")

    print("Loading embeddings...")
    embeddings = get_embeddings()

    print("Uploading to Qdrant...")
    upload_to_qdrant(chunks, embeddings)
    print("Upload complete!")