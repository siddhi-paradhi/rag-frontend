from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Any
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from langgraph.graph.state import StateGraph
from qdrant_client import QdrantClient
from typing import TypedDict
import json
import asyncio
import os

load_dotenv()

app = FastAPI(title="RAG API", description="RAG System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    positive: bool

TOGETHER_key = os.getenv("TOGETHER_API_KEY")
TOGETHER_base = os.getenv("TOGETHER_API_BASE")

os.environ["OPENAI_API_KEY"] = TOGETHER_key
os.environ["OPENAI_API_BASE"] = TOGETHER_base

try:
    print("Connecting to Qdrant...")
    qdrant = QdrantClient(host="localhost", port=6333)
    collections = qdrant.get_collections()
    print(f"Qdrant collections: {collections}")

    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vectorstore = QdrantVectorStore(
        client=qdrant,
        collection_name="website_rag",
        embedding=embedding_model,
        content_payload_key="page_content"
    )

    retriever = vectorstore.as_retriever()

    print("Setting up LLM...")
    prompt_template = PromptTemplate(
        input_variables=["context", "question"],
        template="""
You are ComAI, a helpful and friendly assistant for Commedia Solutions. 
Answer the question using only the context below. Be casual and clear.

Context:
{context}

Question: {question}
Answer:"""
    )

    llm = ChatOpenAI(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        temperature=0.2,
        top_p=0.95
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt_template}
    )

    class RagState(TypedDict):
        question: str
        answer: str
        sources: List[Any]

    def rag_node(state: RagState) -> RagState:
        query = state["question"]
        print(f"Processing query: {query}")
        try:
            result = qa_chain.invoke(query)
            answer = result.get("result", "Sorry, I couldn't find anything.")
            sources = []

            seen = set()
            for doc in result.get("source_documents", []):
                src = doc.metadata.get("source", "unknown")
                if src not in seen:
                    seen.add(src)
                    sources.append(src)

            return {
                "question": query,
                "answer": answer,
                "sources": sources
            }

        except Exception as e:
            print(f"Error in rag_node: {e}")
            return {
                "question": query,
                "answer": "Oops! Something went wrong. Try again later.",
                "sources": []
            }

    builder = StateGraph(RagState)
    builder.add_node("rag_chain", rag_node)
    builder.set_entry_point("rag_chain")
    builder.set_finish_point("rag_chain")
    graph = builder.compile()
    print("RAG system initialized successfully!")

except Exception as e:
    print(f"Fatal RAG startup error: {e}")
    graph = None

@app.get("/")
def read_root():
    return {"message": "RAG API is running", "status": "healthy"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "rag_initialized": graph is not None}

@app.post("/feedback")
async def receive_feedback(feedback: FeedbackRequest):
    try:
        with open("feedback_log.jsonl", "a") as f:
            f.write(feedback.json() + "\n")
    except Exception as e:
        print(f"Feedback write error: {e}")
    return {"status": "success"}

@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    print(f"Received query: {request.question}")
    if not graph:
        raise HTTPException(status_code=500, detail="RAG system not initialized")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    lower_q = request.question.strip().lower()
    casual = {
        "okay": "Okay! Let me know if you need anything else.",
        "ok": "Okay! Let me know if you need anything else.",
        "thanks": "You're very welcome!",
        "thank you": "Happy to help!",
        "hi": "Hey there! What would you like to know about Commedia?",
        "hello": "Hello! Ask me anything about Commedia Solutions.",
        "hey": "Hey there! What would you like to know about Commedia?"
    }

    if lower_q in casual:
        return QueryResponse(answer=casual[lower_q], sources=[])

    state = {
        "question": request.question,
        "answer": "",
        "sources": []
    }

    result = graph.invoke(state)
    return QueryResponse(answer=result["answer"], sources=result["sources"])

@app.post("/query-stream")
async def query_rag_stream(request: QueryRequest):
    print(f"Received streaming query: {request.question}")
    
    async def generate():
        if not graph:
            yield json.dumps({"type": "error", "content": "RAG system not initialized"}) + "\n"
            return
        
        if not request.question.strip():
            yield json.dumps({"type": "error", "content": "Question cannot be empty"}) + "\n"
            return
        
        # Handle casual responses
        lower_q = request.question.strip().lower()
        casual = {
            "okay": "Okay! Let me know if you need anything else.",
            "ok": "Okay! Let me know if you need anything else.",
            "thanks": "You're very welcome!",
            "thank you": "Happy to help!",
            "hi": "Hey there! What would you like to know about Commedia?",
            "hello": "Hello! Ask me anything about Commedia Solutions.",
            "hey": "Hey there! What would you like to know about Commedia?"
        }
        
        if lower_q in casual:
            # Stream the casual response
            response = casual[lower_q]
            for char in response:
                yield json.dumps({"type": "token", "content": char}) + "\n"
                await asyncio.sleep(0.02)  # Small delay for streaming effect
            yield json.dumps({"type": "done"}) + "\n"
            return
        
        # Process with RAG
        state = {
            "question": request.question,
            "answer": "",
            "sources": []
        }
        
        try:
            result = graph.invoke(state)
            answer = result["answer"]
            sources = result["sources"]
            
            # Stream the answer token by token
            for char in answer:
                yield json.dumps({"type": "token", "content": char}) + "\n"
                await asyncio.sleep(0.02)  # Small delay for streaming effect
            
            # Send sources
            if sources:
                yield json.dumps({"type": "sources", "content": sources}) + "\n"
            
            # Send completion signal
            yield json.dumps({"type": "done"}) + "\n"
            
        except Exception as e:
            print(f"Streaming error: {e}")
            yield json.dumps({"type": "error", "content": "Something went wrong. Please try again."}) + "\n"
    
    return StreamingResponse(generate(), media_type="text/plain")