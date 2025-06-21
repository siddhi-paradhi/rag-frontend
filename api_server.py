from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Any
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
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
    memoryContext: str | None = None

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    follow_ups: list[str]  

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
        input_variables=["context", "memoryContext", "input"],
        template="""
You are ComAI, a helpful and friendly assistant for Commedia Solutions. 
Answer the question using only the context below. Be casual and clear.

Context:
{context}

Conversation History:
{memoryContext}

Question: {input}
Answer:"""
    )

    # Follow-up questions prompt template
    followup_prompt = PromptTemplate(
        input_variables=["question", "answer"],
        template="""
Based on the original question and answer about Commedia Solutions, generate 3 relevant follow-up questions that a user might naturally ask next. 
Make them specific, business-relevant, and focused on Commedia Solutions services or information.

Original Question: {question}
Answer: {answer}

Generate exactly 3 follow-up questions as a JSON array. Example format:
["What services does Commedia provide?", "How can I contact Commedia?", "What industries does Commedia serve?"]

Follow-up Questions:"""
    )

    llm = ChatOpenAI(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        temperature=0.2,
        top_p=0.95
    )

    # Separate LLM instance for follow-up generation (higher temperature for creativity)
    followup_llm = ChatOpenAI(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        temperature=0.2,
        top_p=0.95
    )

    # Create custom RAG chain that supports memoryContext
    document_chain = create_stuff_documents_chain(llm, prompt_template)
    rag_chain = create_retrieval_chain(retriever, document_chain)

    class RagState(TypedDict):
        question: str
        answer: str
        sources: List[Any]
        follow_ups: List[str]
        memoryContext: str

    def generate_followup_questions(question: str, answer: str) -> List[str]:
        """Generate follow-up questions using LLM"""
        try:
            
            casual_keywords = ["thanks", "thank you", "hi", "hello", "hey", "okay", "ok"]
            if any(keyword in question.lower() for keyword in casual_keywords):
                return []
            
            prompt = followup_prompt.format(question=question, answer=answer)
            response = followup_llm.invoke(prompt)

            # Parse JSON response
            try:
                import re
                # Extract JSON array from response
                json_match = re.search(r'\[.*?\]', response.content, re.DOTALL)
                if json_match:
                    follow_ups = json.loads(json_match.group())
                    # Ensure we have exactly 3 questions and they're strings
                    if isinstance(follow_ups, list) and len(follow_ups) >= 3:
                        return [str(q) for q in follow_ups[:3]]
            except:
                pass
            
            # Fallback to predefined follow-ups
            return get_fallback_followups(question, answer)
            
        except Exception as e:
            print(f"Error generating follow-ups: {e}")
            return get_fallback_followups(question, answer)

    def get_fallback_followups(question: str, answer: str) -> List[str]:
        """Fallback follow-up questions based on keywords"""
        question_lower = question.lower()
        
        if "service" in question_lower or "what does" in question_lower:
            return [
                "How can I contact Commedia Solutions?",
                "What industries does Commedia serve?",
                "Can you tell me more about Commedia's experience?"
            ]
        elif "contact" in question_lower or "reach" in question_lower:
            return [
                "What services does Commedia provide?",
                "What are Commedia's business hours?",
                "Does Commedia offer consultations?"
            ]
        elif "price" in question_lower or "cost" in question_lower:
            return [
                "What services are included in Commedia's packages?",
                "How can I get a quote from Commedia?",
                "Does Commedia offer custom solutions?"
            ]
        else:
            return [
                "What services does Commedia Solutions provide?",
                "How can I contact Commedia Solutions?",
                "Can you tell me more about Commedia's expertise?"
            ]

    def rag_node(state: RagState) -> RagState:
        query = state["question"]
        memory_context = state.get("memoryContext", "")
        print(f"Processing query: {query}")
        print(f"Memory context: {memory_context}")
        try:
            # Use the custom RAG chain that supports memoryContext
            chain_input = {
                "input": query,  # New chain expects "input" not "query"
                "memoryContext": memory_context
            }
            print(f"Chain input: {chain_input}")
            
            result = rag_chain.invoke(chain_input)

            answer = result.get("answer", "Sorry, I couldn't find anything.")
            sources = []
            seen = set()
            
            # Extract sources from context documents
            for doc in result.get("context", []):
                src = doc.metadata.get("source", "unknown")
                if src not in seen:
                    seen.add(src)
                    sources.append(src)

            # Generate follow-up questions
            follow_ups = generate_followup_questions(query, answer)

            return {
                "question": query,
                "answer": answer,
                "sources": sources,
                "follow_ups": follow_ups,
                "memoryContext": memory_context
            }

        except Exception as e:
            print(f"Error in rag_node: {e}")
            import traceback
            traceback.print_exc()
            return {
                "question": query,
                "answer": "Oops! Something went wrong. Try again later.",
                "sources": [],
                "follow_ups": [],
                "memoryContext": memory_context
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
        return QueryResponse(answer=casual[lower_q], sources=[], follow_ups=[])

    # Fixed: Simplified memoryContext handling
    state = {
        "question": request.question,
        "answer": "",
        "sources": [],
        "follow_ups": [],
        "memoryContext": request.memoryContext or "",
    }

    result = graph.invoke(state)
    return QueryResponse(
        answer=result["answer"], 
        sources=result["sources"],
        follow_ups=result["follow_ups"]
    )

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
                await asyncio.sleep(0.000002)  # Much faster streaming
            yield json.dumps({"type": "done"}) + "\n"
            return
        
        # Process with RAG
        # Fixed: Proper memoryContext handling
        state = {
            "question": request.question,
            "answer": "",
            "sources": [],
            "follow_ups": [],
            "memoryContext": request.memoryContext or "",
        }
        
        try:
            result = graph.invoke(state)
            answer = result["answer"]
            sources = result["sources"]
            follow_ups = result["follow_ups"]
            
            # Stream the answer token by token
            for char in answer:
                yield json.dumps({"type": "token", "content": char}) + "\n"
                await asyncio.sleep(0.002)  # Much faster streaming
            
            # Send sources
            if sources:
                yield json.dumps({"type": "sources", "content": sources}) + "\n"
            
            # Send follow-up questions
            if follow_ups:
                yield json.dumps({"type": "follow_ups", "content": follow_ups}) + "\n"
            
            # Send completion signal
            yield json.dumps({"type": "done"}) + "\n"
            
        except Exception as e:
            print(f"Streaming error: {e}")
            yield json.dumps({"type": "error", "content": "Something went wrong. Please try again."}) + "\n"
    
    return StreamingResponse(generate(), media_type="text/plain")