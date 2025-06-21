'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Send, Loader2, MessageCircle, BookOpen, User, Bot, Sun, Moon, Plus, Sparkles, LogOut, Menu, Trash2, ChevronDown, ChevronUp, ThumbsUp, ThumbsDown, ChevronRight } from 'lucide-react'
import { useSession, signOut } from 'next-auth/react'
import { DatabaseService } from '../lib/database'
import { Conversation } from '../lib/supabase'
import { v4 as uuidv4 } from 'uuid'

interface QueryResponse {
  answer: string
  sources: string[]
  follow_ups: string[]
}

interface Message {
  id: string
  type: 'user' | 'assistant'
  content: string
  sources?: string[]
  followUps?: string[]
  timestamp: Date
  loading?: boolean
  streaming?: boolean
  feedback?: 'up' | 'down'
  sourcesOpen?: boolean
}

interface StreamChunk {
  type: 'token' | 'sources' | 'follow_ups' | 'done' | 'error'
  content?: string | string[]
}

export default function Home() {
  const { data: session, status } = useSession()
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)
  const [showSidebar, setShowSidebar] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Load conversations on mount
  useEffect(() => {
    if (session?.user?.email) {
      loadConversations()
    }
  }, [session])

  const loadConversations = async () => {
    try {
      const convs = await DatabaseService.getConversations(session?.user?.email || '')
      setConversations(convs)
    } catch (error) {
      console.error('Error loading conversations:', error)
    }
  }

  const loadConversation = async (conversationId: string) => {
    try {
      const msgs = await DatabaseService.getMessages(conversationId)
      const formattedMessages: Message[] = msgs.map((msg: any) => ({
        id: msg.id,
        type: msg.type,
        content: msg.content,
        sources: msg.sources,
        followUps: msg.follow_ups || [],
        timestamp: new Date(msg.created_at)
      }))
      setMessages(formattedMessages)
      setCurrentConversationId(conversationId)
      setShowSidebar(false)
    } catch (error) {
      console.error('Error loading conversation:', error)
      setError('Failed to load conversation')
    }
  }

  const deleteConversation = async (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await DatabaseService.deleteConversation(conversationId)
      setConversations(prev => prev.filter(c => c.id !== conversationId))
      if (currentConversationId === conversationId) {
        setCurrentConversationId(null)
        setMessages([])
      }
    } catch (error) {
      console.error('Error deleting conversation:', error)
      setError('Failed to delete conversation')
    }
  }

  const handleFollowUpClick = (followUpQuestion: string) => {
    setQuestion(followUpQuestion)
  }

  const toggleSources = (id: string) => {
    setMessages(prev =>
      prev.map(msg =>
        msg.id === id
          ? { ...msg, sourcesOpen: !msg.sourcesOpen }
          : msg
      )
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!question.trim()) {
      setError('Please enter a question')
      return
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    let conversationId = currentConversationId
    if (!conversationId && session?.user?.email) {
      try {
        const title = question.slice(0, 50) + (question.length > 50 ? '...' : '')
        const newConv = await DatabaseService.createConversation(
          session.user.email,
          title
        )
        conversationId = newConv.id
        setCurrentConversationId(conversationId)
        setConversations(prev => [newConv, ...prev])
      } catch (error) {
        console.error('Error creating conversation:', error)
        setError('Failed to create conversation')
        return
      }
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: question.trim(),
      timestamp: new Date()
    }

    const streamingMessage: Message = {
      id: (Date.now() + 1).toString(),
      type: 'assistant',
      content: '',
      timestamp: new Date(),
      streaming: true
    }

    setMessages(prev => [...prev, userMessage, streamingMessage])
    setQuestion('')
    setLoading(true)
    setError(null)

    if (conversationId) {
      try {
        await DatabaseService.addMessage(conversationId, 'user', userMessage.content)
      } catch (error) {
        console.error('Error saving user message:', error)
      }
    }

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const memoryContext = messages
  .map(m => `${m.type}: ${m.content}`)
  .join('\n');
      const response = await fetch('http://localhost:8010/query-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: userMessage.content,
          context: memoryContext
        }),
        signal: abortController.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('Failed to get response reader')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let finalAnswer = ''
      let finalSources: string[] = []
      let finalFollowUps: string[] = []

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.trim()) {
              try {
                const chunk: StreamChunk = JSON.parse(line)

                setMessages(prev => prev.map(msg => {
                  if (msg.id === streamingMessage.id) {
                    if (chunk.type === 'token') {
                      const newContent = msg.content + (chunk.content || '')
                      finalAnswer = newContent
                      return {
                        ...msg,
                        content: newContent,
                        streaming: true
                      }
                    } else if (chunk.type === 'sources') {
                      finalSources = chunk.content as string[]
                      return {
                        ...msg,
                        sources: finalSources,
                        streaming: true
                      }
                    } else if (chunk.type === 'follow_ups') {
                      finalFollowUps = chunk.content as string[]
                      return {
                        ...msg,
                        followUps: finalFollowUps,
                        streaming: true
                      }
                    } else if (chunk.type === 'done') {
                      return {
                        ...msg,
                        streaming: false
                      }
                    } else if (chunk.type === 'error') {
                      return {
                        ...msg,
                        content: typeof chunk.content === 'string' ? chunk.content : 'An error occurred',
                        streaming: false
                      }
                    }
                  }
                  return msg
                }))
              } catch (parseError) {
                console.error('Failed to parse chunk:', line, parseError)
              }
            }
          }
        }

        if (conversationId && finalAnswer) {
          try {
            await DatabaseService.addMessage(
              conversationId,
              'assistant',
              finalAnswer,
              finalSources,
              finalFollowUps
            )
          } catch (error) {
            console.error('Error saving assistant message:', error)
          }
        }

      } finally {
        reader.releaseLock()
      }

    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Request was aborted')
        setMessages(prev => prev.filter(msg => msg.id !== streamingMessage.id))
      } else {
        console.error('Streaming error:', err)
        setError(err.message || 'Failed to get response. Make sure your backend is running.')
        setMessages(prev => prev.map(msg =>
          msg.id === streamingMessage.id
            ? { ...msg, content: 'Sorry, something went wrong. Please try again.', streaming: false }
            : msg
        ))
      }
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleFeedback = useCallback(async (messageId: string, type: 'up' | 'down') => {
    setMessages(prev =>
      prev.map(msg =>
        msg.id === messageId ? { ...msg, feedback: type } : msg
      )
    )
    const message = messages.find(msg => msg.id === messageId)
    if (!message) return

    try {
      await fetch('http://localhost:8010/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: message.content,
          answer: message.content,
          positive: type === 'up',
        })
      })
    } catch (err) {
      console.error('Feedback error:', err)
    }
  }, [messages])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleLogout = () => {
    signOut({ callbackUrl: '/login' })
  }

  const exampleQuestions = [
    "What services does Commedia provide?",
    "Where is Commedia located?",
    "What is unique about Commedia?",
    "How does the Commedia team operate?"
  ]

  const clearChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setMessages([])
    setCurrentConversationId(null)
    setError(null)
    setLoading(false)
  }

  const StreamingIndicator = () => (
    <div className="flex items-center gap-2 py-1">
      <div className="flex gap-1">
        <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${
          darkMode ? 'bg-gray-500' : 'bg-gray-400'
        }`} style={{ animationDelay: '0ms', animationDuration: '1.2s' }}></div>
        <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${
          darkMode ? 'bg-gray-500' : 'bg-gray-400'
        }`} style={{ animationDelay: '200ms', animationDuration: '1.2s' }}></div>
        <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${
          darkMode ? 'bg-gray-500' : 'bg-gray-400'
        }`} style={{ animationDelay: '400ms', animationDuration: '1.2s' }}></div>
      </div>
    </div>
  )

  // Follow-up Questions Component
  const FollowUpQuestions = ({ followUps }: { followUps: string[] }) => (
    <div className="mt-4 space-y-3">
      <div className="flex items-center gap-2">
        <ChevronRight size={14} className={darkMode ? 'text-gray-400' : 'text-gray-500'} />
        <span className={`text-xs font-medium ${
          darkMode ? 'text-gray-400' : 'text-gray-500'
        }`}>
          Ask a follow-up:
        </span>
      </div>
      <div className="space-y-2">
        {followUps.map((followUp, index) => (
          <button
            key={index}
            onClick={() => handleFollowUpClick(followUp)}
            className={`w-full text-left p-3 rounded-xl border text-sm transition-all duration-200 hover:scale-[1.01] group ${
              darkMode
                ? 'border-gray-700 bg-gray-800/50 hover:bg-gradient-to-r hover:from-purple-600/20 hover:to-blue-600/20 hover:border-purple-500/50 text-gray-300 hover:text-white'
                : 'border-gray-200 bg-gray-50 hover:bg-gradient-to-r hover:from-purple-50 hover:to-blue-50 hover:border-purple-300 text-gray-700 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="flex-1 pr-2">{followUp}</span>
              <ChevronRight
                size={16}
                className={`transition-transform duration-200 group-hover:translate-x-1 ${
                  darkMode ? 'text-gray-500 group-hover:text-purple-400' : 'text-gray-400 group-hover:text-purple-500'
                }`}
              />
            </div>
          </button>
        ))}
      </div>
    </div>
  )

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
      </div>
    )
  }

  return (
    <div className={`flex h-screen transition-all duration-300 ${darkMode
      ? 'bg-gradient-to-br from-black via-blue-950 to-red-950'
      : 'bg-gradient-to-tr from-blue-100 via-white to-red-200'
    }`}>
      {/* Sidebar */}
      <div className={`${showSidebar ? 'fixed' : 'hidden'} lg:${showSidebar ? 'block' : 'hidden'} inset-0 z-50 lg:relative lg:z-0 lg:w-80`}>
        <div
          className="absolute inset-0 bg-black/50 lg:hidden"
          onClick={() => setShowSidebar(false)}
        />
        <div className={`absolute left-0 top-0 h-full w-80 transform transition-transform lg:relative lg:translate-x-0 ${
          darkMode ? 'bg-gray-900 border-r border-gray-800' : 'bg-white border-r border-gray-200'
        }`}>
          <div className={`p-4 border-b ${darkMode ? 'border-gray-800' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <h3 className={`font-semibold ${darkMode ? 'text-white' : 'text-gray-900'}`}>
                Chat History
              </h3>
              <button
                onClick={() => setShowSidebar(false)}
                className={`lg:hidden p-1 rounded ${
                  darkMode ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-100 text-gray-600'
                }`}
              >
                ×
              </button>
            </div>
          </div>
          <div className="overflow-y-auto h-full p-4 space-y-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={`group relative rounded-lg transition-colors ${
                  currentConversationId === conv.id
                    ? darkMode ? 'bg-blue-900/50' : 'bg-blue-100'
                    : darkMode ? 'hover:bg-gray-800' : 'hover:bg-gray-100'
                }`}
              >
                <button
                  onClick={() => loadConversation(conv.id)}
                  className="w-full text-left p-3 rounded-lg"
                >
                  <div className={`font-medium truncate ${
                    darkMode ? 'text-white' : 'text-gray-900'
                  }`}>
                    {conv.title}
                  </div>
                  <div className={`text-sm ${
                    darkMode ? 'text-gray-400' : 'text-gray-500'
                  }`}>
                    {new Date(conv.updated_at).toLocaleDateString()}
                  </div>
                </button>
                <button
                  onClick={(e) => deleteConversation(conv.id, e)}
                  className={`absolute right-2 top-3 opacity-0 group-hover:opacity-100 p-1 rounded transition-all ${
                    darkMode ? 'hover:bg-red-900/50 text-red-400' : 'hover:bg-red-100 text-red-600'
                  }`}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {conversations.length === 0 && (
              <div className={`text-center py-8 ${
                darkMode ? 'text-gray-500' : 'text-gray-400'
              }`}>
                No conversations yet
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className={`backdrop-blur-md border-b px-6 py-4 flex items-center justify-between ${
          darkMode
            ? 'bg-black/90 border-gray-800'
            : 'bg-white/80 border-gray-200/50'
        }`}>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className={`p-2.5 rounded-xl transition-all duration-200 hover:scale-105 ${
                darkMode
                  ? 'hover:bg-gray-900 text-gray-500'
                  : 'hover:bg-gray-100 text-gray-500'
              }`}
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-xl ${
                darkMode
                  ? 'bg-gradient-to-r from-purple-600 to-blue-600'
                  : 'bg-gradient-to-r from-purple-500 to-blue-500'
              }`}>
                <MessageCircle className="text-white" size={20} />
              </div>
              <div>
                <h1 className={`text-xl font-bold ${
                  darkMode ? 'text-white' : 'text-gray-900'
                }`}>
                  Com AI
                </h1>
                <p className={`text-sm ${
                  darkMode ? 'text-gray-400' : 'text-gray-500'
                }`}>
                  AI-powered knowledge assistant for Commedia
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={clearChat}
              className={`p-2.5 rounded-xl transition-all duration-200 hover:scale-105 ${
                darkMode
                  ? 'hover:bg-gray-900 text-gray-500'
                  : 'hover:bg-gray-100 text-gray-500'
              }`}
              title="New Chat"
            >
              <Plus size={20} />
            </button>
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={`p-2.5 rounded-xl transition-all duration-200 hover:scale-105 ${
                darkMode
                  ? 'hover:bg-gray-900 text-yellow-400'
                  : 'hover:bg-gray-100 text-gray-600'
              }`}
            >
              {darkMode ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            {session && (
              <div className="flex items-center gap-2 ml-2">
                <div className={`text-sm ${darkMode ? 'text-gray-300' : 'text-gray-700'}`}>
                  {session.user?.email}
                </div>
                <button
                  onClick={handleLogout}
                  className={`p-2.5 rounded-xl transition-all duration-200 hover:scale-105 ${
                    darkMode
                      ? 'hover:bg-red-900/50 text-red-400'
                      : 'hover:bg-red-100 text-red-600'
                  }`}
                  title="Logout"
                >
                  <LogOut size={20} />
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="max-w-4xl mx-auto space-y-6">
            {messages.length === 0 && (
              <div className="text-center space-y-8">
                <div className="space-y-4">
                  <div className={`inline-flex p-4 rounded-2xl ${
                    darkMode
                      ? 'bg-gradient-to-r from-purple-600/20 to-blue-600/20'
                      : 'bg-gradient-to-r from-purple-100 to-blue-100'
                  }`}>
                    <Sparkles className={`${
                      darkMode ? 'text-purple-400' : 'text-purple-600'
                    }`} size={32} />
                  </div>
                  <h2 className={`text-3xl font-bold ${
                    darkMode ? 'text-white' : 'text-gray-900'
                  }`}>
                    Welcome to Com AI
                  </h2>
                  <p className={`text-lg ${
                    darkMode ? 'text-gray-400' : 'text-gray-600'
                  }`}>
                    Ask me anything about Commedia's services, locations, and expertise.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl mx-auto">
                  {exampleQuestions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setQuestion(q)}
                      className={`p-4 rounded-xl text-left transition-all duration-200 hover:scale-[1.02] ${
                        darkMode
                          ? 'bg-gray-900 hover:bg-gray-800 text-gray-300 border border-gray-800'
                          : 'bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 shadow-sm hover:shadow-md'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <MessageCircle className={`mt-0.5 ${
                          darkMode ? 'text-purple-400' : 'text-purple-500'
                        }`} size={16} />
                        <span className="text-sm">{q}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-4 ${
                  message.type === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {/* Assistant Avatar */}
                {message.type === 'assistant' ? (
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                    darkMode
                      ? 'bg-gradient-to-r from-purple-600 to-blue-600'
                      : 'bg-gradient-to-r from-purple-500 to-blue-500'
                  }`}>
                    <Bot className="text-white" size={16} />
                  </div>
                ) : (
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                    darkMode ? 'bg-gray-700' : 'bg-gray-200'
                  }`}>
                    <User className={darkMode ? 'text-gray-300' : 'text-gray-600'} size={16} />
                  </div>
                )}

                {/* Message Content */}
                <div className={`max-w-3xl ${message.type === 'user' ? 'order-first' : ''}`}>
                  <div className={`rounded-2xl px-6 py-4 ${
                    message.type === 'user'
                      ? darkMode
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white'
                        : 'bg-gradient-to-r from-purple-500 to-blue-500 text-white'
                      : darkMode
                        ? 'bg-gray-900 text-gray-100 border border-gray-800'
                        : 'bg-white text-gray-900 border border-gray-200 shadow-sm'
                  } ${message.streaming ? 'animate-pulse' : ''}`}>
                    <div className="prose prose-sm max-w-none">
                      {message.content}
                    </div>

                    {message.streaming && <StreamingIndicator />}

                    {/* Collapsible sources */}
                    {message.sources && message.sources.length > 0 && (
                      <div className="mt-4 pt-4 border-t border-gray-200/20">
                        <button
                          className="flex items-center gap-2 text-xs font-semibold mb-2 focus:outline-none"
                          onClick={() => toggleSources(message.id)}
                        >
                          <BookOpen size={14} className={darkMode ? 'text-gray-400' : 'text-gray-600'} />
                          <span className={`${darkMode ? 'text-red-400' : 'text-blue-700'} uppercase tracking-wide`}>Sources</span>
                          {message.sourcesOpen
                            ? <ChevronUp size={16} />
                            : <ChevronDown size={16} />}
                        </button>
                        {message.sourcesOpen && (
                          <div className="space-y-1">
                            {message.sources.map((source, i) => (
                              <div key={i} className={`text-xs break-all
                                ${darkMode ? 'text-blue-200' : 'text-blue-900'}
                              `}>
                                {source}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Feedback UI */}
                    {message.type === 'assistant' && !message.streaming && (
                      <div className="mt-4 flex gap-2">
                        <button
                          className={`rounded-full p-1 transition-colors border
                            ${message.feedback === 'up'
                              ? 'bg-blue-700 text-white border-blue-700'
                              : 'hover:bg-blue-100 text-blue-700 border-blue-300'
                            }`}
                          title="Thumbs up"
                          disabled={!!message.feedback}
                          onClick={() => handleFeedback(message.id, 'up')}
                        >
                          <ThumbsUp size={18} />
                        </button>
                        <button
                          className={`rounded-full p-1 transition-colors border
                            ${message.feedback === 'down'
                              ? 'bg-red-700 text-white border-red-700'
                              : 'hover:bg-red-100 text-red-700 border-red-300'
                            }`}
                          title="Thumbs down"
                          disabled={!!message.feedback}
                          onClick={() => handleFeedback(message.id, 'down')}
                        >
                          <ThumbsDown size={18} />
                        </button>
                        {message.feedback === 'up' && <span className="text-xs text-blue-600 ml-2">Thanks for your feedback!</span>}
                        {message.feedback === 'down' && <span className="text-xs text-red-600 ml-2">We appreciate your input!</span>}
                      </div>
                    )}

                    {/* Follow-up questions section */}
                    {message.type === 'assistant' && message.followUps && message.followUps.length > 0 && !message.streaming && (
                      <FollowUpQuestions followUps={message.followUps} />
                    )}
                  </div>

                  <div className={`flex items-center gap-2 mt-2 text-xs ${
                    darkMode ? 'text-gray-500' : 'text-gray-400'
                  }`}>
                    {message.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}

            {error && (
              <div className={`p-4 rounded-xl ${
                darkMode
                  ? 'bg-red-900/20 border border-red-800 text-red-300'
                  : 'bg-red-50 border border-red-200 text-red-700'
              }`}>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                  <span className="text-sm font-medium">Error</span>
                </div>
                <p className="text-sm mt-1">{error}</p>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className={`backdrop-blur-md border-t px-6 py-4 ${
          darkMode
            ? 'bg-black/90 border-gray-800'
            : 'bg-white/80 border-gray-200/50'
        }`}>
          <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
            <div className={`relative rounded-2xl overflow-hidden ${
              darkMode
                ? 'bg-gray-900 border border-gray-800'
                : 'bg-white border border-gray-200 shadow-sm'
            }`}>
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask me anything about Commedia..."
                className={`w-full px-6 py-4 pr-20 resize-none focus:outline-none transition-all duration-200 ${
                  darkMode
                    ? 'bg-transparent text-white placeholder-gray-500'
                    : 'bg-transparent text-gray-900 placeholder-gray-400'
                }`}
                rows={1}
                style={{
                  minHeight: '24px',
                  maxHeight: '120px',
                  height: 'auto',
                }}
                onInput={(e) => {
                  const target = e.target as HTMLTextAreaElement
                  target.style.height = 'auto'
                  target.style.height = target.scrollHeight + 'px'
                }}
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className={`absolute right-3 top-1/2 transform -translate-y-1/2 p-2.5 rounded-xl transition-all duration-200 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed ${
                  darkMode
                    ? 'bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500'
                    : 'bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600'
                } text-white`}
              >
                {loading ? (
                  <Loader2 className="animate-spin" size={18} />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>

            <div className={`mt-3 text-xs text-center ${
              darkMode ? 'text-gray-500' : 'text-gray-400'
            }`}>
              Press Enter to send, Shift+Enter for new line
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}