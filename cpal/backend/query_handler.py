import asyncio
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    lang: str = "en"
    memoryContext: Optional[str] = None

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    positive: bool

@router.post("/api/query")
async def query_rag(request: QueryRequest, fastapi_request: Request):  # Fixed: Added FastAPI Request
    """
    Process RAG query with Claude
    """
    try:
        # Get clients from app state - Fixed: Use fastapi_request instead of request
        rag_system = fastapi_request.app.state.rag_system
        translator = fastapi_request.app.state.translation_service
        
        # Handle translation - Fixed: Use request.lang instead of detecting
        question_en = request.question
        detected_lang = request.lang
        
        # Only translate if not English
        if detected_lang != "en":
            question_en, detected_lang = translator.translate_if_needed(request.question)
        
        memory_context_en = request.memoryContext or ""
        if memory_context_en and detected_lang != "en":
            memory_context_en = translator.translate_text(
                memory_context_en, detected_lang, "en"
            )
        
        # Use the complete RAG pipeline
        answer_en = await rag_system.generate_answer(question_en, top_k=5)
        
        # Log the answer for debugging
        logger.info(f"Generated answer: {answer_en[:100]}...")
        logger.info(f"Question lang: {request.lang}, Detected lang: {detected_lang}")
        
        # Generate follow-ups if claude_client is available
        followups_en = []
        if hasattr(fastapi_request.app.state, 'claude_client') and fastapi_request.app.state.claude_client:
            try:
                followups_en = fastapi_request.app.state.claude_client.generate_followup_questions(
                    question_en, answer_en, ""
                )
            except Exception as e:
                logger.warning(f"Failed to generate follow-ups: {e}")
                followups_en = []
        
        # Translate response if needed - Fixed: Use request.lang for consistency
        if request.lang != "en":
            answer = translator.translate_text(answer_en, "en", request.lang)
            followups = [
                translator.translate_text(q, "en", request.lang) 
                for q in followups_en
            ]
        else:
            answer = answer_en
            followups = followups_en
        
        sources = rag_system.get_last_sources()
        
        return {
            "answer": answer,
            "sources": sources[:3],
            "follow_ups": followups
        }
        
    except Exception as e:
        logger.error(f"Error in query_rag: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/api/stream")
async def stream_rag(request: Request):
    """
    Stream RAG response with improved error handling
    """
    try:
        # Get clients from app state
        rag_system = request.app.state.rag_system
        translator = request.app.state.translation_service
        
        body = await request.json()
        user_question = body.get("question", "")
        lang = body.get("lang", "en")
        memory_context = body.get("memoryContext", "")

        logger.info(f"Streaming request: question='{user_question[:50]}...', lang={lang}")
        
        # Handle translation - Fixed: Use lang parameter directly for English
        question_en = user_question
        detected_lang = lang
        
        # Only translate if not English
        if lang != "en":
            question_en, detected_lang = translator.translate_if_needed(user_question)
        
        memory_context_en = memory_context
        if memory_context and detected_lang != "en":
            memory_context_en = translator.translate_text(memory_context, detected_lang, "en")

        # For English: Stream word by word - Fixed: Use lang parameter instead of detected_lang
        if lang == "en":
            async def english_stream():
                try:
                    # Get the complete RAG response
                    full_response = await rag_system.generate_answer(question_en, top_k=5)
                    
                    if not full_response or full_response.strip() == "":
                        yield json.dumps({
                            "type": "token",
                            "content": "I don't have specific information about that topic. Please try rephrasing your question."
                        }) + "\n"
                        yield json.dumps({"type": "done"}) + "\n"
                        return
                    
                    # Stream the response word by word for better UX
                    words = full_response.split()
                    for i, word in enumerate(words):
                        chunk = word + (" " if i < len(words) - 1 else "")
                        yield json.dumps({
                            "type": "token",
                            "content": chunk
                        }) + "\n"
                        
                        # Small delay to make streaming visible
                        await asyncio.sleep(0.05)
                   
                    # Generate follow-ups if available
                    followups = []
                    if hasattr(request.app.state, 'claude_client') and request.app.state.claude_client:
                        try:
                            followups = request.app.state.claude_client.generate_followup_questions(
                                question_en, full_response, ""
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate follow-ups: {e}")
                    
                    yield json.dumps({
                        "type": "follow_ups",
                        "content": followups
                    }) + "\n"

                    yield json.dumps({"type": "done"}) + "\n"
                    
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    yield json.dumps({
                        "type": "error",
                        "content": f"I apologize, but I'm having trouble generating a response right now."
                    }) + "\n"
                    yield json.dumps({"type": "done"}) + "\n"

            return StreamingResponse(
                english_stream(),
                media_type="application/json",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "X-Accel-Buffering": "no"
                }
            )

        else:
            # For non-English: Generate full response then translate
            try:
                full_response = await rag_system.generate_answer(question_en, top_k=5)
                
                if not full_response or full_response.strip() == "":
                    fallback_msg = "I don't have specific information about that topic. Please try rephrasing your question."
                    translated_fallback = translator.translate_text(fallback_msg, "en", lang)
                    
                    return StreamingResponse(
                        iter([
                            json.dumps({"type": "token", "content": translated_fallback}) + "\n",
                            json.dumps({"type": "follow_ups", "content": []}) + "\n",
                            json.dumps({"type": "done"}) + "\n"
                        ]),
                        media_type="application/json",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Access-Control-Allow-Origin": "*",
                            "X-Accel-Buffering": "no"
                        }
                    )

                # Translate the response
                translated = translator.translate_text(full_response, "en", lang)

                # Generate follow-ups if available
                followups = []
                if hasattr(request.app.state, 'claude_client') and request.app.state.claude_client:
                    try:
                        followups_en = request.app.state.claude_client.generate_followup_questions(
                            question_en, full_response, ""
                        )
                        followups = [
                            translator.translate_text(q, "en", lang)
                            for q in followups_en
                        ]
                    except Exception as e:
                        logger.warning(f"Follow-up generation error: {e}")
                        followups = translator.get_default_followups(lang)

                return StreamingResponse(
                    iter([
                        json.dumps({"type": "token", "content": translated}) + "\n",
                        json.dumps({"type": "follow_ups", "content": followups}) + "\n",
                        json.dumps({"type": "done"}) + "\n"
                    ]),
                    media_type="application/json",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "X-Accel-Buffering": "no"
                    }
                )
                
            except Exception as e:
                logger.error(f"Error generating response for non-English: {e}")
                error_msg = "I apologize, but I'm having trouble generating a response right now."
                translated_error = translator.translate_text(error_msg, "en", lang)
                
                return StreamingResponse(
                    iter([
                        json.dumps({"type": "token", "content": translated_error}) + "\n",
                        json.dumps({"type": "follow_ups", "content": []}) + "\n",
                        json.dumps({"type": "done"}) + "\n"
                    ]),
                    media_type="application/json",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                        "X-Accel-Buffering": "no"
                    }
                )

    except Exception as e:
        logger.error(f"Error in stream_rag: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """
    Handle user feedback
    """
    try:
        logger.info(f"Feedback received: {'positive' if feedback.positive else 'negative'}")
        logger.info(f"Question: {feedback.question[:100]}...")
        logger.info(f"Answer: {feedback.answer[:100]}...")
        
        # TODO: Store feedback in database or analytics service
        
        return {
            "message": "Feedback received successfully",
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error handling feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to process feedback")

@router.get("/api/health")
async def health_check(request: Request):
    """
    Health check endpoint
    """
    try:
        rag_system = request.app.state.rag_system
        health_status = rag_system.health_check()
        
        return {
            "status": "healthy" if all(health_status.values()) else "degraded",
            "details": health_status
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@router.post("/api/debug")
async def debug_search(request: Request):
    """
    Debug endpoint to test search functionality
    """
    try:
        body = await request.json()
        query = body.get("query", "")
        
        if not query:
            raise HTTPException(status_code=400, detail="Query parameter is required")
        
        rag_system = request.app.state.rag_system
        debug_info = await rag_system.debug_search(query)
        
        return debug_info
    except Exception as e:
        logger.error(f"Debug search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))