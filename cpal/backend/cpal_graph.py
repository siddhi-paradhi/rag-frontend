import logging
from typing import Dict, Any, List, Optional, TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws.chat_models import ChatBedrock
from backend.rag_system import RAGSystem
import asyncio
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CPALState(TypedDict):
    """State schema for CPAL graph"""
    query: str
    context: Optional[str]
    output: Optional[str]
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]
    retrieval_score: Optional[float]
    needs_clarification: bool

class CPALGraphSystem:
    """Production-ready RAG system with LangGraph orchestration"""
    
    def __init__(self, 
                 max_context_length: int = 8000,
                 min_confidence_threshold: float = 0.3,
                 enable_self_correction: bool = True):
        self.rag = RAGSystem()
        self.max_context_length = max_context_length
        self.min_confidence_threshold = min_confidence_threshold
        self.enable_self_correction = enable_self_correction
        
        self.llm = ChatBedrock(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            region_name="us-east-1",  
            model_kwargs={
                "temperature": 0.2,
                "max_tokens": 300,
            },
            streaming=False
        )
        
        self.graph = self._build_graph()
        self.executor = self.graph.compile()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(CPALState)
        
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("quality_check", self._quality_check_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("fallback", self._fallback_node)
        
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "quality_check")
        
        workflow.add_conditional_edges(
            "quality_check",
            self._should_proceed_to_generate,
            {
                "generate": "generate",
                "fallback": "fallback"
            }
        )
        
        workflow.add_edge("generate", "validate")
        
        if self.enable_self_correction:
            workflow.add_conditional_edges(
                "validate",
                self._should_accept_answer,
                {
                    "accept": END,
                    "retry": "generate",
                    "fallback": "fallback"
                }
            )
        else:
            workflow.add_edge("validate", END)
        
        workflow.add_edge("fallback", END)
        
        return workflow
    
    async def _retrieve_node(self, state: CPALState) -> Dict[str, Any]:
        """Retrieve relevant context from RAG system"""
        try:
            query = state["query"]
            logger.info(f"Retrieving context for query: {query[:100]}...")
            
            context_data = await self.rag.get_context(query)
            
            logger.info(f"RAG returned: {type(context_data)}")
            
            if isinstance(context_data, dict):
                context = context_data.get("context", "")
                score = context_data.get("avg_score", 0.0)
                metadata = context_data.get("metadata", {})
            else:
                context = str(context_data)
                score = 0.5
                metadata = {}
                
            logger.info(f"context length: {len(context)}, score: {score}")
            
            if len(context) > self.max_context_length:
                context = context[:self.max_context_length] + "..."
                logger.warning(f"Context truncated to {self.max_context_length} characters")
            
            return {
                "context": context,
                "retrieval_score": score,
                "metadata": metadata,
                "needs_clarification": False
            }
            
        except Exception as e:
            logger.error(f"Error in retrieve_node: {e}")
            return {
                "context": "",
                "error": f"Retrieval failed: {str(e)}",
                "retrieval_score": 0.0,
                "metadata": {},
                "needs_clarification": True
            }
    
    async def _quality_check_node(self, state: CPALState) -> Dict[str, Any]:
        """Check if retrieved context is sufficient"""
        context = state.get("context", "")
        score = state.get("retrieval_score", 0.0)
    
    # Debug logging
        logger.info(f"Quality check - Context length: {len(context)}, Score: {score}")
    
        if not context or len(context.strip()) < 10:
           logger.warning("Retrieved context is too short or empty")
           return {"needs_clarification": True}
    
    # Make the threshold more lenient or remove it temporarily for debugging
        if score < 0.3: 
           logger.warning(f"Retrieval confidence {score} below threshold 0.3")
           return {"needs_clarification": True}
    
        logger.info("Quality check passed")
        return {"needs_clarification": False}
    
    def _should_proceed_to_generate(self, state: CPALState) -> str:
        """Decide whether to generate answer or use fallback"""
        return "fallback" if state.get("needs_clarification", False) else "generate"
    
    async def _generate_node(self, state: CPALState) -> Dict[str, Any]:
        """Generate answer using Claude"""
        try:
            context = state["context"]
            query = state["query"]
            
            system_message = SystemMessage(content=self._get_system_prompt())
            human_message = HumanMessage(content=self._get_user_prompt(context, query))
            
            logger.info("Generating answer with Claude...")
            
            response = self.llm.invoke([system_message, human_message])
            
            return {
                "output": response.content,
                "metadata": {
                    **state.get("metadata", {}),
                    "generation_timestamp": datetime.now().isoformat(),
                    "model_used": "claude-3-sonnet-bedrock"
                }
            }
            
        except Exception as e:
            logger.error(f"Error in generate_node: {e}")
            return {
                "error": f"Generation failed: {str(e)}",
                "output": None
            }
    
    async def _validate_node(self, state: CPALState) -> Dict[str, Any]:
        """Validate the generated answer"""
        output = state.get("output", "")
        
        if not output or len(output.strip()) < 5:
            logger.warning("Generated output is too short")
            return {"needs_clarification": True}
        
        hallucination_phrases = [
            "I don't have access to",
            "I cannot find",
            "I'm not sure",
            "I apologize, but I don't have"
        ]
        
        if any(phrase in output.lower() for phrase in hallucination_phrases):
            logger.info("Answer indicates uncertainty - this is good!")
        
        return {"needs_clarification": False}
    
    def _should_accept_answer(self, state: CPALState) -> str:
        """Decide whether to accept the answer or retry"""
        if state.get("error"):
            return "fallback"
        
        if state.get("needs_clarification", False):

            metadata = state.get("metadata", {})
            retry_count = metadata.get("retry_count", 0)
            
            if retry_count >= 2: 
                return "fallback"
            
            metadata["retry_count"] = retry_count + 1
            return "retry"
        
        return "accept"
    
    async def _fallback_node(self, state: CPALState) -> Dict[str, Any]:
        """Handle cases where main flow fails"""
        query = state["query"]
        error = state.get("error", "")
        
        logger.info(f"Using fallback for query: {query[:50]}...")
        
        fallback_response = (
            "I'm sorry, I couldn't find that information in our Commedia Solutions records. "
            "This might be because:\n"
            "• The information isn't in our current knowledge base\n"
            "• Your question might need to be more specific\n"
            "• There might be a temporary system issue\n\n"
            "Please try rephrasing your question or contact our support team for assistance."
        )
        
        return {
            "output": fallback_response,
            "metadata": {
                **state.get("metadata", {}),
                "fallback_used": True,
                "original_error": error,
                "fallback_timestamp": datetime.now().isoformat()
            }
        }
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for Claude"""
        return """You are CPAL, the internal assistant for Commedia Solutions. Always address commedia solutions in first person plural. 
        When asked a question, provide an accurate answer based on the context provided. Always answer in 3-4 lines, concise and to the point. Don't over explain anything but never leave the user with an incomplete answer.

CRITICAL INSTRUCTIONS:
1. You can ONLY answer using the context provided below
2. If the answer is not in the context, you MUST say: "I'm sorry, I couldn't find that information in our records."
3. Never guess, assume, or make up information
4. Never mention names, dates, or details not explicitly stated in the context
5. Be helpful but stay strictly within the provided information
6. If the context is unclear or incomplete, ask for clarification rather than guessing

Your responses should be:
- Accurate and based solely on the provided context
- Professional and helpful
- Concise but complete
- Clear about any limitations in the available information"""
    
    def _get_user_prompt(self, context: str, query: str) -> str:
        """Get the user prompt with context and query"""
        return f"""Context from Commedia Solutions records:
{context}

Question: {query}

Please provide an accurate answer based solely on the context above. If the information isn't available in the context, please say so clearly."""
    
    async def query(self, user_query: str) -> Dict[str, Any]:
        """Main entry point for querying the system"""
        try:
            initial_state = CPALState(
                query=user_query,
                context=None,
                output=None,
                error=None,
                metadata={"start_time": datetime.now().isoformat()},
                retrieval_score=None,
                needs_clarification=False
            )
            
            logger.info(f"Processing query: {user_query[:100]}...")
           
            result = await self.executor.ainvoke(initial_state)
            
            result["metadata"]["end_time"] = datetime.now().isoformat()
            result["metadata"]["success"] = result.get("output") is not None
            
            return result
            
        except Exception as e:
            logger.error(f"Error in query execution: {e}")
            return {
                "query": user_query,
                "output": "I'm sorry, there was a system error. Please try again later.",
                "error": str(e),
                "metadata": {"error": True, "timestamp": datetime.now().isoformat()}
            }

cpal_system = CPALGraphSystem(
    max_context_length=8000,
    min_confidence_threshold=0.3,
    enable_self_correction=True
)

async def query_cpal(user_query: str) -> Dict[str, Any]:
    """Main function to query CPAL system"""
    return await cpal_system.query(user_query)

cpal_graph_executor = cpal_system.executor