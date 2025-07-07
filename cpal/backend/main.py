import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
from pydantic import BaseModel
from dotenv import load_dotenv

from backend.query_handler import router as query_router
from backend.cpal_graph import query_cpal

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

claude_client = None
rag_system = None
translation_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    """
    global claude_client, rag_system, translation_service

    logger.info("Starting Commedia Solutions RAG API with Claude Sonnet...")

    try:
        from backend.claude_client import ClaudeClient
        from backend.rag_system import RAGSystem
        from backend.translation_service import TranslationService
        
        claude_client = ClaudeClient(
            region=os.getenv("AWS_REGION", "us-east-1")
        )
        logger.info("Claude client initialized")

        rag_system = RAGSystem()
        logger.info("RAG system initialized")

        translation_service = TranslationService()
        logger.info("Translation service initialized")
        
        app.state.claude_client = claude_client
        app.state.rag_system = rag_system
        app.state.translation_service = translation_service
        
        
        logger.info("All services initialized successfully!")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        raise

    yield

    logger.info("Shutting down services...")

app = FastAPI(
    title="Commedia Solutions RAG API",
    description="Advanced RAG system powered by Claude Sonnet via Amazon Bedrock",
    version="4.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
    
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "claude_client": claude_client is not None,
            "rag_system": rag_system is not None,
            "translation_service": translation_service is not None,
            
        }
    }

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Commedia Solutions RAG API with Claude Sonnet",
        "version": "4.0.0",
        "endpoints": {
            "/docs": "API documentation",
            "/health": "Health check",
            "/query": "Legacy query endpoint",
            "/cpal_query": "LangGraph-powered query endpoint"
        }
    }

class CPALQueryRequest(BaseModel):
    query: str

@app.post("/cpal_query")
async def cpal_query_endpoint(payload: CPALQueryRequest):
    """
    Query the CPAL LangGraph-powered system.
    Expects: {"query": "<user question>"}
    """
    user_query = payload.query
    if not user_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body")
    result = await query_cpal(user_query)
    return result

app.include_router(query_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="info"
    )