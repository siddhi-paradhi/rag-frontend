import { NextRequest } from 'next/server';

export const runtime = 'edge';

const API_BASE = process.env.RAG_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  try {
    const { messages, lang = 'en', memoryContext = '' } = await req.json();

    const lastMessage = messages[messages.length - 1];
    const question = lastMessage?.content || '';

    const response = await fetch(`${API_BASE}/query-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question, lang, memoryContext }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
      },
    });
  } catch (error) {
    console.error('API Error:', error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
}