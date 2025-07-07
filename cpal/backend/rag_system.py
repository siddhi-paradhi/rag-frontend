import os
import logging
import json
import asyncio
from typing import List, Optional
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
load_dotenv()

class RAGSystem:
    """
    Production-ready RAG retriever using Qdrant and AWS Titan.
    Handles context retrieval, health checks, document search, and response generation.
    """
    def __init__(self):
        self.qdrant_url = os.getenv("QDRANT_URL")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY")
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "WEB_DATA")
        self.region = os.getenv("AWS_REGION", "us-east-1")

        self.qdrant_client: Optional[QdrantClient] = None
        self.bedrock = None
        self.last_sources: List[str] = []
        self.max_context_length = 8000  # Limit context size

        self._initialize_clients()

    def _initialize_clients(self) -> None:
        try:
            self.qdrant_client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.qdrant_api_key,
                timeout=30  # Increased timeout
            )
            collections = self.qdrant_client.get_collections()
            logger.info(f"Connected to Qdrant. Collections: {collections}")
            
            # Check if our collection exists and has data
            if self.collection_name in [c.name for c in collections.collections]:
                collection_info = self.qdrant_client.get_collection(self.collection_name)
                count = self.qdrant_client.count(collection_name=self.collection_name)
                logger.info(f"Collection '{self.collection_name}' found with {count.count} points")
                logger.info(f"Collection config: {collection_info.config.params.vectors}")
            else:
                logger.error(f"Collection '{self.collection_name}' not found!")
                
        except Exception as e:
            logger.error(f"Qdrant connection failed: {e}")
            self.qdrant_client = None

        try:
            self.bedrock = boto3.client(
                "bedrock-runtime", 
                region_name=self.region,
                config=boto3.session.Config(
                    retries={'max_attempts': 3},
                    read_timeout=60
                )
            )
            logger.info("Amazon Bedrock client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            self.bedrock = None

    async def embed_with_titan(self, text: str) -> List[float]:
        """Async wrapper for Titan embedding"""
        if not self.bedrock:
            raise ValueError("Bedrock client not initialized")
            
        def _embed():
            try:
                body = {"inputText": text[:8000]}  # Limit input size
                response = self.bedrock.invoke_model(
                    body=json.dumps(body),
                    modelId="amazon.titan-embed-text-v1",
                    accept="application/json",
                    contentType="application/json"
                )
                response_body = json.loads(response['body'].read())
                return response_body['embedding']
            except ClientError as e:
                logger.error(f"Bedrock embedding error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected embedding error: {e}")
                raise
        
        # Run in thread pool to avoid blocking
        return await asyncio.get_event_loop().run_in_executor(None, _embed)

    async def get_context(self, query: str, top_k: int = 5) -> str:
        if not self.qdrant_client or not self.bedrock:
            logger.warning("RAG system not properly initialized")
            return ""

        try:
            embedding_task = asyncio.create_task(self.embed_with_titan(query))
            query_embedding = await embedding_task
            logger.info(f"Query: '{query}' (embedding dim: {len(query_embedding)})")
            
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=0.2  
            )
            
            if not search_results:
                logger.warning("no search results found")
                return ""
            
            logger.info(f"Search returned {len(search_results)} results")
            
            contexts = []
            sources = []
            total_length = 0
            
            for point in search_results:
                # Try multiple possible content field names
                content = (
                    point.payload.get("page_content") or 
                    point.payload.get("content") or 
                    point.payload.get("text") or
                    point.payload.get("document") or
                    ""
                )
                
                if content and str(content).strip():
                    content_str = str(content).strip()
                    
                    # Check if adding this content would exceed max length
                    if total_length + len(content_str) > self.max_context_length:
                        remaining_space = self.max_context_length - total_length
                        if remaining_space > 50:  
                            content_str = content_str[:remaining_space] + "..."
                            contexts.append(content_str)
                        break
                    
                    contexts.append(content_str)
                    total_length += len(content_str)
                    logger.debug(f"Added content (score: {point.score:.3f}, length: {len(content_str)})")
                
                source = (
                    point.payload.get("source") or 
                    point.payload.get("url") or 
                    point.payload.get("file") or
                    point.payload.get("filename") or
                    ""
                )
                if source and source not in sources:
                    sources.append(source)
            
            self.last_sources = sources
            
            if contexts:
                combined_context = "\n\n".join(contexts)
                logger.info(f"Retrieved {len(contexts)} contexts (total length: {len(combined_context)})")
                return combined_context
            else:
                logger.warning("No valid contexts found")
                return ""
                    
        except Exception as e:
            logger.error(f"Context retrieval error: {e}")
            return ""

    async def generate_response_with_llm(self, query: str, context: str) -> str:
        """
        Generate a response using AWS Bedrock with Claude.
        """
        if not self.bedrock:
            return "Language model not available."

        if not context.strip():
            return "I don't have specific information about that topic in my knowledge base. Please try rephrasing your question or ask about other aspects of Commedia Solutions."

        # Create a professional prompt that matches your chatbot's style
        prompt = f"""You are CPAL – a professional, conversational assistant for Commedia Solutions. Your job is to provide natural, helpful, and confident answers to user questions based on the provided context.

Your responses must follow these rules:
- NEVER begin with "Based on the context provided" or robotic phrases like "According to the documents."
- Speak like a human expert who knows Commedia Solutions deeply.
- Always answer in 3-4 lines, concise and to the point. Don't over explain anything but never leave the user with an incomplete answer.
- Summarize clearly without repeating lines from the context verbatim.
- Do NOT mention the word "context" or "document."
- Keep the tone friendly, clear, and informative — imagine you're speaking to a curious, intelligent person.
- Use everyday business language — avoid legalistic or overly technical jargon unless asked specifically.
- Never fabricate details. If something is not present in the context, politely admit it or say "I don't have that information right now."
- Avoid filler words and over-apologizing.
- Don't mention sources or documents directly, just provide the information needed.
- When asked about Commedia Solutions, respond in the first person (e.g., "We, at Commedia Solutions, provide...").
- When asked about leadership team, always respond first with Our leadership team at Commedia Solutions is composed of experienced and dynamic individuals. Our Founder and Managing Director, C S Raghava Rao, brings 25 years of experience in the telecom industry.

Context:
{context}

User Question: {query}

Please provide a helpful and accurate response based on the context provided:"""

        try:
            def _generate():
                body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 500,
                    "temperature": 0.1,
                    "anthropic_version": "bedrock-2023-05-31"
                }
                
                response = self.bedrock.invoke_model(
                    body=json.dumps(body),
                    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                    accept="application/json",
                    contentType="application/json"
                )
                
                response_body = json.loads(response['body'].read())
                
                # Handle different response formats
                if 'content' in response_body and isinstance(response_body['content'], list):
                    if len(response_body['content']) > 0 and 'text' in response_body['content'][0]:
                        return response_body['content'][0]['text']
                elif 'completion' in response_body:
                    return response_body['completion']
                else:
                    logger.error(f"Unexpected response format: {response_body}")
                    return "I apologize, but I'm having trouble generating a response right now."
            
            # Run in thread pool to avoid blocking
            return await asyncio.get_event_loop().run_in_executor(None, _generate)
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"Bedrock API error ({error_code}): {e}")
            
            if error_code == 'ThrottlingException':
                return "I'm experiencing high demand right now. Please try again in a moment."
            elif error_code == 'ValidationException':
                return "There was an issue with your request. Please try rephrasing your question."
            else:
                return "I'm having trouble accessing my language model right now. Please try again."
                
        except Exception as e:
            logger.error(f"LLM response generation error: {e}")
            return "I apologize, but I'm having trouble generating a response right now."

    async def generate_answer(self, query: str, top_k: int = 5) -> str:
        """
        Complete RAG pipeline: retrieve context and generate response.
        This is the main method your chatbot should call.
        """
        try:
            # Step 1: Retrieve relevant context
            context = await self.get_context(query, top_k)
            
            # Step 2: Generate response using LLM with the retrieved context
            response = await self.generate_response_with_llm(query, context)
            return response
            
        except Exception as e:
            logger.error(f"Error in generate_answer: {e}")
            return "I apologize, but I'm experiencing technical difficulties. Please try again."

    def get_last_sources(self) -> List[str]:
        return self.last_sources

    def health_check(self) -> dict:
        return {
            "qdrant_connected": self.qdrant_client is not None,
            "bedrock_connected": self.bedrock is not None,
            "collection_name": self.collection_name,
            "embed_model": "amazon.titan-embed-text-v1",
            "max_context_length": self.max_context_length
        }

    async def search_documents(
        self,
        query: str,
        top_k: int = 10,
        score_threshold: float = 0.2
    ) -> List[dict]:
        if not self.qdrant_client or not self.bedrock:
            return []

        try:
            query_embedding = await self.embed_with_titan(query)
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold
            )
            documents = []
            for point in search_results:
                doc = {
                    "id": point.id,
                    "score": point.score,
                    "content": (
                        point.payload.get("page_content") or 
                        point.payload.get("content") or 
                        ""
                    ),
                    "source": point.payload.get("source", ""),
                    "metadata": point.payload
                }
                documents.append(doc)
            return documents
        except Exception as e:
            logger.error(f"Document search error: {e}")
            return []

    async def debug_search(self, query: str) -> dict:
        """Debug method to check what's happening with the search"""
        if not self.qdrant_client or not self.bedrock:
            return {"error": "Clients not initialized"}
        
        try:
            # Check collection info
            collection_info = self.qdrant_client.get_collection(self.collection_name)
            count = self.qdrant_client.count(collection_name=self.collection_name)
            
            # Try the search
            query_embedding = await self.embed_with_titan(query)
            
            # Search without score threshold first
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=10,
                with_payload=True,
                with_vectors=False
            )
            
            # Print details of first few results
            debug_results = []
            for i, result in enumerate(search_results[:3]):
                debug_results.append({
                    "rank": i + 1,
                    "score": result.score,
                    "payload_keys": list(result.payload.keys()),
                    "content_preview": str(result.payload.get('page_content', result.payload.get('content', '')))[:100]
                })
            
            return {
                "collection_points": count.count,
                "search_results": len(search_results),
                "first_score": search_results[0].score if search_results else None,
                "embedding_dim": len(query_embedding),
                "debug_results": debug_results
            }
            
        except Exception as e:
            logger.error(f"Debug error: {e}")
            return {"error": str(e)}