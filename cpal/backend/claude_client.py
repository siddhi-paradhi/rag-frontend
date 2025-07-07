import boto3
import json
import asyncio
import logging
from typing import Optional, AsyncGenerator, List
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class ClaudeClient:
    def __init__(self, region: str = "us-east-1", model_id: Optional[str] = None):
        """
        Initialize Claude client with Bedrock runtime
        """
        self.region = region
        self.model_id = model_id or "anthropic.claude-3-sonnet-20240229-v1:0"
        self.bedrock = boto3.client("bedrock-runtime", region_name=region)
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def query_async(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 300,
        top_p: float = 0.95
    ) -> str:
        """
        Async wrapper for Claude query
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._query_sync,
            prompt,
            system_prompt,
            temperature,
            max_tokens,
            top_p
        )
    
    async def query(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 300,
        top_p: float = 0.95
    ) -> str:
        """
        Async query method (alias for query_async) - needed for non-English branch
        """
        return await self.query_async(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p
        )
    
    def _query_sync(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 300,
        top_p: float = 0.95
    ) -> str:
        """
        Synchronous Claude query
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "messages": messages
            }
            
            if system_prompt:
                body["system"] = system_prompt
            
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                body=json.dumps(body)
            )
            
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
            
        except Exception as e:
            logger.error(f"Claude query error: {e}")
            raise Exception(f"Claude API error: {str(e)}")
    
    async def stream_query_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 300,
        top_p: float = 0.95
    ) -> AsyncGenerator[str, None]:
        """
        Stream Claude response (Bedrock streaming)
        """
        try:
            messages = [{"role": "user", "content": prompt}]
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "messages": messages
            }
            
            if system_prompt:
                body["system"] = system_prompt
            
            response = self.bedrock.invoke_model_with_response_stream(
                modelId=self.model_id,
                contentType="application/json",
                body=json.dumps(body)
            )
            
            for event in response["body"]:
                chunk = event.get("chunk")
                if chunk:
                    chunk_data = json.loads(chunk["bytes"].decode())
                    
                    if chunk_data["type"] == "content_block_delta":
                        if "delta" in chunk_data and "text" in chunk_data["delta"]:
                            yield chunk_data["delta"]["text"]
                    elif chunk_data["type"] == "message_stop":
                        break
                        
        except Exception as e:
            logger.error(f"Claude streaming error: {e}")
            raise Exception(f"Claude streaming error: {str(e)}")
    
    async def summarize_response(self, full_response: str) -> str:
        """
        Summarize a long response into 3 short, natural sentences using Claude
        """
        summary_prompt = f"""Summarize the following assistant response in 3 short, natural-sounding sentences. Use simple language and avoid any robotic phrasing.

Response:
{full_response}"""
        
        try:
            return await self.query_async(
                prompt=summary_prompt,
                system_prompt="You're a helpful assistant who summarizes long responses naturally.",
                temperature=0.2,
                max_tokens=300
            )
        except Exception as e:
            logger.error(f"Error summarizing response: {e}")
            return "Sorry, I had trouble summarizing that response."
    
    def generate_followup_questions(
        self,
        question: str,
        answer: str,
        context: str = "",
        num_questions: int = 3
    ) -> List[str]:
        """
        Generate relevant follow-up questions using Claude
        Args:
            question (str): The original user question.
            answer (str): The answer provided by Claude.
            context (str, optional): Additional context for the conversation.
            num_questions (int, optional): Number of follow-up questions to generate.

        Returns:
            List[str]: List of follow-up questions.
        """
        prompt = f"""Based on the following conversation, generate {num_questions} highly relevant and specific follow-up questions that a user might naturally ask next.

Original Question: {question}
Answer Provided: {answer}
Context: {context}

Requirements:
- Questions should be directly related to the specific content discussed
- Avoid generic questions
- Make them natural and conversational
- Focus on practical next steps or deeper understanding

Return only the questions, one per line, with no numbering or formatting."""

        try:
            response = self._query_sync(
                prompt=prompt,
                temperature=0.1,
                max_tokens=100
            )
            
            questions = [
                q.strip() 
                for q in response.split('\n') 
                if q.strip() and not q.strip().startswith(('1.', '2.', '3.', '-', '*'))
            ]
            
            return questions[:num_questions]
            
        except Exception as e:
            logger.error(f"Error generating follow-ups: {e}")
            return [
                "What services does Commedia Solutions offer?",
                "How can I contact Commedia Solutions?",
                "Tell me about Commedia's expertise."
            ]
    
    def close(self):
        self.executor.shutdown(wait=True)

    def __del__(self):
        self.close()