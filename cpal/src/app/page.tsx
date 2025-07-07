'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, X, Trash2, AlertTriangle,
  Download, User, Globe, ExternalLink, Copy, Shield, Info, ThumbsUp, ThumbsDown
} from 'lucide-react';

// --- Types ---
interface Message {
  id: string;
  type: 'user' | 'bot';
  text: string;
  timestamp: number;
  status?: 'sending' | 'sent' | 'error';
  followUps?: string[];
  streaming?: boolean;
  feedback?: 'up' | 'down' | null;
  error?: boolean;
  sources?: string[] | null;
  rag_used?: boolean;
  language?: string;
}

interface ChatState {
  isMinimized: boolean;
  isTyping: boolean;
}

interface LanguageOption {
  code: string;
  name: string;
  native: string;
}

const TRANSLATIONS = {
  en: {
    welcome: "Hello! I'm your dedicated AI guide, ready to assist you with any inquiries related to Commedia Solutions. How can I help you today?",
    defaultFollowUps: [
      "What services does Commedia Solutions offer?",
      "How can I contact Commedia Solutions?",
      "Tell me about Commedia's expertise."
    ],
    typing: "CPal is typing...",
    online: "Online • Available 24/7",
    offline: "Offline • We'll respond soon",
    placeholder: "Type your message in English...",
    sendMessage: "Send message",
    clearConversation: "Clear Conversation",
    clearConfirmText: "Are you sure you want to clear all messages? This action cannot be undone.",
    cancel: "Cancel",
    clearAll: "Clear All",
    chatMinimized: "Chat minimized. Click the maximize button to continue.",
    askFollowUp: "Ask a follow up:",
    helpful: "Helpful",
    notHelpful: "Not helpful",
    sources: "Sources:",
    offlineWarning: "You're offline. Messages will be sent when connection is restored.",
    errorMessage: "Sorry, I'm having trouble connecting to the backend right now. Please try again later.",
    exportTitle: "Save conversation",
    selectLanguage: "Select language",
    disclaimer: "Disclaimer: We collect your responses to improve your experience"
  },
  ar: {
    welcome: "مرحباً! أنا مرشدك الذكي المختص، مستعد لمساعدتك في أي استفسارات متعلقة بحلول كوميديا. كيف يمكنني مساعدتك اليوم؟",
    defaultFollowUps: [
      "ما هي الخدمات التي تقدمها كوميديا سوليوشنز؟",
      "كيف يمكنني التواصل مع كوميديا سوليوشنز؟",
      "أخبرني عن خبرة كوميديا."
    ],
    typing: "سيبال يكتب...",
    online: "متصل • متاح 24/7",
    offline: "غير متصل • سنرد قريبًا",
    placeholder: "اكتب رسالتك بالعربية...",
    sendMessage: "إرسال الرسالة",
    clearConversation: "مسح المحادثة",
    clearConfirmText: "هل أنت متأكد من أنك تريد مسح جميع الرسائل؟ لا يمكن التراجع عن هذا الإجراء.",
    cancel: "إلغاء",
    clearAll: "مسح الكل",
    chatMinimized: "تم تصغير الدردشة. انقر على زر التكبير للمتابعة.",
    askFollowUp: "اسأل سؤال متابعة:",
    helpful: "مفيد",
    notHelpful: "غير مفيد",
    sources: "المصادر:",
    offlineWarning: "أنت غير متصل. سيتم إرسال الرسائل عند استعادة الاتصال.",
    errorMessage: "عذراً، أواجه مشكلة في الاتصال بالخادم الآن. يرجى المحاولة مرة أخرى لاحقاً.",
    exportTitle: "حفظ المحادثة",
    selectLanguage: "اختر اللغة",
    disclaimer: "إخلاء المسؤولية: نجمع ردودك لتحسين تجربتك"
  },
  hi: {
    welcome: "नमस्ते! मैं आपका समर्पित AI गाइड हूं, कॉमेडिया सॉल्यूशंस से संबंधित किसी भी प्रश्न में आपकी सहायता के लिए तैयार हूं। आज मैं आपकी कैसे मदद कर सकता हूं?",
    defaultFollowUps: [
      "कॉमेडिया सॉल्यूशंस कौन सी सेवाएं प्रदान करता है?",
      "मैं कॉमेडिया सॉल्यूशंस से कैसे संपर्क कर सकता हूं?",
      "कॉमेडिया की विशेषज्ञता के बारे में बताएं।"
    ],
    typing: "सीपाल टाइप कर रहा है...",
    online: "ऑनलाइन • 24/7 उपलब्ध",
    offline: "ऑफलाइन • हम जल्द ही जवाब देंगे",
    placeholder: "हिंदी में अपना संदेश टाइप करें...",
    sendMessage: "संदेश भेजें",
    clearConversation: "बातचीत साफ़ करें",
    clearConfirmText: "क्या आप वाकई सभी संदेशों को साफ़ करना चाहते हैं? यह क्रिया पूर्ववत नहीं की जा सकती।",
    cancel: "रद्द करें",
    clearAll: "सब साफ़ करें",
    chatMinimized: "चैट छोटा किया गया। जारी रखने के लिए बड़ा करें बटन पर क्लिक करें।",
    askFollowUp: "फॉलो-अप प्रश्न पूछें:",
    helpful: "सहायक",
    notHelpful: "सहायक नहीं",
    sources: "स्रोत:",
    offlineWarning: "आप ऑफलाइन हैं। कनेक्शन बहाल होने पर संदेश भेजे जाएंगे।",
    errorMessage: "खुशी, मुझे अभी बैकएंड से जुड़ने में परेशानी हो रही है। कृपया बाद में पुनः प्रयास करें।",
    exportTitle: "बातचीत सहेजें",
    selectLanguage: "भाषा चुनें",
    disclaimer: "अस्वीकरण: हम आपके अनुभव को बेहतर बनाने के लिए आपकी प्रतिक्रियाएं एकत्र करते हैं"
  },
  zh: {
    welcome: "您好！我是您的专属AI助手，随时准备协助您解答与Commedia Solutions相关的任何问题。今天我可以为您做些什么？",
    defaultFollowUps: [
      "Commedia Solutions提供什么服务？",
      "我如何联系Commedia Solutions？",
      "告诉我Commedia的专业领域。"
    ],
    typing: "CPal正在输入...",
    online: "在线 • 全天候服务",
    offline: "离线 • 我们会尽快回复",
    placeholder: "用中文输入您的消息...",
    sendMessage: "发送消息",
    clearConversation: "清除对话",
    clearConfirmText: "您确定要清除所有消息吗？此操作无法撤销。",
    cancel: "取消",
    clearAll: "全部清除",
    chatMinimized: "聊天已最小化。点击最大化按钮继续。",
    askFollowUp: "提出后续问题：",
    helpful: "有帮助",
    notHelpful: "无帮助",
    sources: "来源：",
    offlineWarning: "您处于离线状态。连接恢复后将发送消息。",
    errorMessage: "抱歉，我现在无法连接到后端服务器。请稍后重试。",
    exportTitle: "保存对话",
    selectLanguage: "选择语言",
    disclaimer: "免责声明：我们收集您的回复以改善您的体验"
  }
};

const CHAT_CONFIG = {
  MAX_MESSAGE_LENGTH: 500,
  TYPING_DELAY: 1000,
  AUTO_SCROLL_THRESHOLD: 180,
  ANIMATION_DURATION: 300,
  DEBOUNCE_DELAY: 300,
} as const;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

const DEFAULT_LANGUAGES: LanguageOption[] = [
  { code: "en", name: "English", native: "English" },
  { code: "ar", name: "Arabic", native: "العربية" },
  { code: "hi", name: "Hindi", native: "हिन्दी" },
  { code: "zh", name: "Mandarin", native: "中文" }
];

const useDebounce = (value: string, delay: number) => {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
};

const CommediaChatbotFloating: React.FC = () => {
  // --- State ---
  const [chatState, setChatState] = useState<ChatState>({ isMinimized: false, isTyping: false });
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [isClient, setIsClient] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [streamingMsg, setStreamingMsg] = useState('');
  const [feedbackLoading, setFeedbackLoading] = useState<string | null>(null);
  const [languages] = useState<LanguageOption[]>(DEFAULT_LANGUAGES);
  const [selectedLanguage, setSelectedLanguage] = useState<LanguageOption>(DEFAULT_LANGUAGES[0]);
  const [showLangMenu, setShowLangMenu] = useState(false);
  const [showChat, setShowChat] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messageIdCounter = useRef(0);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const debouncedMessage = useDebounce(message, CHAT_CONFIG.DEBOUNCE_DELAY);

  const t = useMemo(() => {
    return TRANSLATIONS[selectedLanguage.code as keyof typeof TRANSLATIONS] || TRANSLATIONS.en;
  }, [selectedLanguage.code]);

  useEffect(() => {
    setIsClient(true);
    setIsOnline(typeof window !== "undefined" ? window.navigator.onLine : true);
  }, []);

  useEffect(() => {
    setMessages([{
      id: 'welcome',
      type: 'bot',
      text: t.welcome,
      timestamp: Date.now(),
      status: 'sent',
      followUps: t.defaultFollowUps,
      feedback: null,
      language: selectedLanguage.code
    }]);
  }, [selectedLanguage.code, t.welcome, t.defaultFollowUps]);

  useEffect(() => {
    if (!isClient) return;
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [isClient]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const container = chatContainerRef.current;
    if (container && messagesEndRef.current) {
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < CHAT_CONFIG.AUTO_SCROLL_THRESHOLD;
      if (isNearBottom || behavior === 'auto') {
        messagesEndRef.current.scrollIntoView({ behavior, block: 'end' });
      }
    }
  }, []);

  useEffect(() => {
    scrollToBottom('auto');
  }, [messages.length, chatState.isMinimized, streamingMsg, scrollToBottom]);

  useEffect(() => {
    if (!chatState.isMinimized && inputRef.current) {
      inputRef.current.focus();
    }
  }, [chatState.isMinimized]);

  const generateMessageId = useCallback(() => {
    messageIdCounter.current += 1;
    return `msg_${Date.now()}_${messageIdCounter.current}`;
  }, []);

  const sendMessage = useCallback(
    async (overrideMessage?: string) => {
      const useMsg = typeof overrideMessage === 'string' ? overrideMessage : message;
      const trimmedMessage = useMsg.trim();
      if (!trimmedMessage || trimmedMessage.length > CHAT_CONFIG.MAX_MESSAGE_LENGTH) return;

      const userMessage: Message = {
        id: generateMessageId(),
        type: 'user',
        text: trimmedMessage,
        timestamp: Date.now(),
        status: 'sent',
        language: selectedLanguage.code
      };

      setMessages(prev => [...prev, userMessage]);
      setMessage('');
      setStreamingMsg('');
      setChatState(prev => ({ ...prev, isTyping: true }));

      try {
        const apiBody = {
          question: trimmedMessage,
          lang: selectedLanguage.code,
          memoryContext: ""
        };
        const resp = await fetch(`${API_BASE}/api/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(apiBody),
        });

        if (!resp.body || !resp.ok) throw new Error('Bot error');

        const reader = resp.body.getReader();
        let botMsgId = generateMessageId();
        let fullText = '';
        let followUps: string[] | undefined = undefined;
        let sources: string[] | undefined = undefined;
        let doneFlag = false;

        setMessages(prev => [
          ...prev,
          {
            id: botMsgId,
            type: 'bot',
            text: '',
            timestamp: Date.now(),
            status: 'sent',
            streaming: true,
            feedback: null,
            language: selectedLanguage.code,
          }
        ]);

        const updateStreamingMessage = (t: string) => {
          setStreamingMsg(t);
          setMessages(prev =>
            prev.map(m =>
              m.id === botMsgId ? { ...m, text: t, streaming: true } : m
            )
          );
        };

        let decoder = new TextDecoder();
        let buffer = '';
        while (!doneFlag) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (let line of lines) {
            line = line.trim();
            if (!line) continue;
            try {
              const chunk = JSON.parse(line);
              if (chunk.type === "done") {
                doneFlag = true;
                break;
              }
              if (chunk.type === "token" && typeof chunk.content === 'string') {
                fullText += chunk.content;
                updateStreamingMessage(fullText);
              }
              if (chunk.type === "follow_ups") {
                followUps = chunk.content;
              }
              if (chunk.type === "sources") {
                sources = chunk.content;
              }
              if (chunk.type === "error") {
                doneFlag = true;
                setStreamingMsg('');
                setMessages(prev => [
                  ...prev,
                  {
                    id: generateMessageId(),
                    type: 'bot',
                    text: chunk.content || t.errorMessage,
                    timestamp: Date.now(),
                    status: 'error',
                    error: true,
                    language: selectedLanguage.code,
                  }
                ]);
                setChatState(prev => ({ ...prev, isTyping: false }));
                return;
              }
            } catch {
              continue;
            }
          }
        }

        setStreamingMsg('');
        setMessages(prev =>
          prev.map(m =>
            m.id === botMsgId
              ? {
                ...m,
                text: fullText,
                streaming: false,
                followUps: followUps,
                sources: sources,
                feedback: null,
                language: selectedLanguage.code,
              }
              : m
          )
        );
        setChatState(prev => ({ ...prev, isTyping: false }));

      } catch (err) {
        setStreamingMsg('');
        setMessages(prev => [
          ...prev,
          {
            id: generateMessageId(),
            type: 'bot',
            text: t.errorMessage,
            timestamp: Date.now(),
            status: 'error',
            error: true,
            language: selectedLanguage.code,
          }
        ]);
        setChatState(prev => ({ ...prev, isTyping: false }));
      }
    },
    [message, messages, generateMessageId, selectedLanguage, t.errorMessage]
  );

  const handleFeedback = async (msgId: string, value: 'up' | 'down') => {
    setFeedbackLoading(msgId);
    try {
      const msg = messages.find(m => m.id === msgId);
      if (msg && msg.type === 'bot') {
        const body = {
          question: messages.find(m => m.type === 'user' && m.timestamp < msg.timestamp)?.text || "",
          answer: msg.text,
          positive: value === 'up'
        };
        await fetch(`${API_BASE}/api/feedback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
      }
      setMessages(prev =>
        prev.map(m =>
          m.id === msgId ? { ...m, feedback: value } : m
        )
      );
    } catch (error) { } finally {
      setFeedbackLoading(null);
    }
  };

  const clearMessages = useCallback(() => {
    setMessages([{
      id: 'welcome',
      type: 'bot',
      text: t.welcome,
      timestamp: Date.now(),
      status: 'sent',
      followUps: t.defaultFollowUps,
      feedback: null,
      language: selectedLanguage.code
    }]);
    setShowClearConfirm(false);
  }, [t.welcome, t.defaultFollowUps, selectedLanguage.code]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    if (value.length <= CHAT_CONFIG.MAX_MESSAGE_LENGTH) {
      setMessage(value);
    }
  }, []);

  const handleKeyPress = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }, [sendMessage]);

  const groupedMessages = useMemo(() => {
    const groups: { sender: 'user' | 'bot'; msgs: Message[] }[] = [];
    let lastSender: 'user' | 'bot' | null = null;
    let group: Message[] = [];
    messages.forEach((msg) => {
      if (msg.type === lastSender) {
        group.push(msg);
      } else {
        if (group.length) groups.push({ sender: lastSender as 'user' | 'bot', msgs: group });
        group = [msg];
        lastSender = msg.type;
      }
    });
    if (group.length && lastSender !== null) groups.push({ sender: lastSender as 'user' | 'bot', msgs: group });
    return groups;
  }, [messages]);

  const StatusIndicator = useMemo(() => (
    <motion.div 
      className={`w-3 h-3 rounded-full border-2 border-white shadow-sm transition-all duration-300 ${
        isOnline ? 'bg-green-400' : 'bg-red-400'
      }`}
      animate={isOnline ? { scale: [1, 1.1, 1] } : {}}
      transition={{ repeat: Infinity, duration: 2 }}
    >
      {isClient && isOnline && <div className="w-full h-full bg-green-300 rounded-full animate-pulse" />}
    </motion.div>
  ), [isOnline, isClient]);

  const TypingIndicator = useMemo(() => (
  <AnimatePresence>
    {chatState.isTyping && (
      <motion.div 
        className="flex justify-start mb-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
      >
        <div className="mr-3 flex-shrink-0 w-8 h-8 rounded-full bg-[#388bfd] flex items-center justify-center">
          <div className="w-8 h-8 bg-black rounded-full flex items-center justify-center overflow-hidden">
            <img 
              src="/cpal.png" 
              alt="Logo" 
              className="w-6 h-6 object-contain"
            />
          </div>
        </div>
        <motion.div 
          className="bg-[#111] backdrop-blur-md rounded-2xl px-4 py-3 shadow-lg border border-[#388bfd]/30 max-w-xs"
          animate={{ 
            boxShadow: [
              "0 4px 20px rgba(56, 139, 253, 0.2)",
              "0 4px 30px rgba(56, 139, 253, 0.4)",
              "0 4px 20px rgba(56, 139, 253, 0.2)"
            ]
          }}
          transition={{ repeat: Infinity, duration: 2 }}
        >
          <div className="flex space-x-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-2 h-2 bg-[#388bfd] rounded-full"
                animate={{ 
                  scale: [1, 1.5, 1],
                  opacity: [0.5, 1, 0.5]
                }}
                transition={{ 
                  repeat: Infinity, 
                  duration: 1.2,
                  delay: i * 0.2
                }}
              />
            ))}
          </div>
          <div className="mt-2 text-xs text-white/80">{t.typing}</div>
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
), [chatState.isTyping, t.typing]);

  const formatTimestamp = (timestamp: number): string => {
    const date = new Date(timestamp);
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const ampm = date.getHours() >= 12 ? 'PM' : 'AM';
    const displayHours = date.getHours() % 12 || 12;
    return `${displayHours.toString().padStart(2, '0')}:${minutes} ${ampm}`;
  };

  const exportConversation = () => {
    const history = messages.map(
      m => `[${m.type === 'user' ? 'You' : 'CPal'}] ${m.text}`
    ).join('\n\n');
    const blob = new Blob([history], { type: 'text/plain' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'commedia_chat_history.txt';
    link.click();
  };

  const LanguageSelector = (
    <div className="relative">
      <motion.button
        onClick={() => setShowLangMenu(v => !v)}
        className="w-8 h-8 rounded-lg bg-[#111]/80 backdrop-blur-sm hover:bg-[#222]/90 flex items-center justify-center transition-all duration-200 border border-[#388bfd]/20 focus:outline-none focus:ring-2 focus:ring-[#388bfd]/40"
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.95 }}
        aria-label={t.selectLanguage}
        title={t.selectLanguage}
      >
        <Globe className="w-4 h-4 text-white" />
      </motion.button>
      <AnimatePresence>
        {showLangMenu && (
          <motion.div 
            className="absolute right-0 mt-2 bg-[#111] border border-[#388bfd]/30 rounded-xl shadow-xl z-50 min-w-[140px] py-2 overflow-hidden"
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.2 }}
          >
            {languages.map(lang => (
              <motion.button
                key={lang.code}
                onClick={() => {
                  setSelectedLanguage(lang);
                  setShowLangMenu(false);
                }}
                disabled={selectedLanguage.code === lang.code}
                className={`w-full text-left px-4 py-2 hover:bg-[#388bfd]/20 text-white text-sm rounded-lg transition-colors ${
                  selectedLanguage.code === lang.code ? "bg-[#388bfd]/30 font-bold" : ""
                }`}
                whileHover={{ backgroundColor: "rgba(56, 139, 253, 0.2)" }}
                whileTap={{ scale: 0.98 }}
              >
                {lang.native} ({lang.name})
              </motion.button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${inputRef.current.scrollHeight}px`;
    }
  }, [message, chatState.isMinimized]);

  // --- Floating Button ---
  const floatingButton = (
    <motion.button
      onClick={() => setShowChat(!showChat)}
      className="flex items-center justify-center w-16 h-16 rounded-full bg-black shadow-2xl focus:outline-none focus:ring-2 focus:ring-white/20 overflow-hidden"

      style={{
        position: 'fixed',
        bottom: 32,
        right: 32,
        zIndex: 10000,
      }}
      whileHover={{ 
        scale: 1.1,
        boxShadow: "0 12px 50px rgba(56, 139, 253, 0.4)"
      }}
      whileTap={{ scale: 0.95 }}
      animate={{
        boxShadow: [
          "0 8px 40px rgba(0,0,0,0.9)",
          "0 8px 50px rgba(56, 139, 253, 0.3)",
          "0 8px 40px rgba(0,0,0,0.9)"
        ]
      }}
      transition={{ 
        boxShadow: { repeat: Infinity, duration: 3 },
        scale: { duration: 0.2 }
      }}
      aria-label={showChat ? "Close chat" : "Open chat"}
      title={showChat ? "Close chat" : "Open chat"}
    >
      <AnimatePresence mode="wait">
        {showChat ? (
          <motion.div
            key="close"
            initial={{ opacity: 0, rotate: -180 }}
            animate={{ opacity: 1, rotate: 0 }}
            exit={{ opacity: 0, rotate: 180 }}
            transition={{ duration: 0.3 }}
          >
            <X className="w-9 h-9 text-white" />
          </motion.div>
        ) : (
          <motion.div
            key="cpal"
            initial={{ opacity: 0, rotate: 180 }}
            animate={{ opacity: 1, rotate: 0 }}
            exit={{ opacity: 0, rotate: -180 }}
            transition={{ duration: 0.3 }}
          >
            <div className="w-12 h-12 bg-black rounded-full flex items-center justify-center overflow-hidden">
              <img 
                src="/cpal.png" 
                alt="Logo" 
                className="w-11 h-11 object-contain"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  );

  // --- Chat Window ---
  const chatWindow = (
    <AnimatePresence>
      {showChat && (
        <motion.div
          className="flex flex-col bg-black border border-[#388bfd]/30 rounded-2xl shadow-2xl overflow-hidden"
          style={{
            position: 'fixed',
            bottom: 100, // Above the button
            right: 32,
            width: 420, // Increased width
            height: 600,
            zIndex: 9999,
          }}
          initial={{ opacity: 0, y: 50, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 50, scale: 0.9 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 bg-[#111] border-b border-[#388bfd]/20">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-full bg-[#388bfd] flex items-center justify-center overflow-hidden">
                <div className="w-10 h-10 bg-black rounded-full flex items-center justify-center overflow-hidden">
                  <img 
                    src="/cpal.png" 
                    alt="Logo" 
                    className="w-9 h-9 object-contain"
                  />
                </div>
              </div>
              <div>
                <h3 className="text-white font-semibold text-sm">CPal Assistant</h3>
                <div className="flex items-center space-x-2">
                  {StatusIndicator}
                  <span className="text-xs text-white/70">
                    {isOnline ? t.online : t.offline}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              {LanguageSelector}
              <motion.button
                onClick={exportConversation}
                className="w-8 h-8 rounded-lg bg-[#111]/80 backdrop-blur-sm hover:bg-[#222]/90 flex items-center justify-center transition-all duration-200 border border-[#388bfd]/20 focus:outline-none focus:ring-2 focus:ring-[#388bfd]/40"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                aria-label={t.exportTitle}
                title={t.exportTitle}
              >
                <Download className="w-4 h-4 text-white" />
              </motion.button>
              <motion.button
                onClick={() => setShowClearConfirm(true)}
                className="w-8 h-8 rounded-lg bg-[#111]/80 backdrop-blur-sm hover:bg-red-500/20 flex items-center justify-center transition-all duration-200 border border-[#388bfd]/20 focus:outline-none focus:ring-2 focus:ring-red-500/40"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.95 }}
                aria-label={t.clearConversation}
                title={t.clearConversation}
              >
                <Trash2 className="w-4 h-4 text-white" />
              </motion.button>
            </div>
          </div>

          {/* Messages Container */}
          <div 
            ref={chatContainerRef}
            className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth"
            style={{ scrollbarWidth: 'thin', scrollbarColor: '#388bfd #111' }}
          >
            {groupedMessages.map((group, groupIdx) => (
              <div key={groupIdx} className={`flex ${group.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex items-start space-x-3 max-w-[85%] ${group.sender === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
                  {/* Avatar */}
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                    group.sender === 'user' ? 'bg-white' : 'bg-[#388bfd]'
                  }`}>
                    {group.sender === 'user' ? (
                      <User className="w-5 h-5 text-black" />
                    ) : (
                      <div className="w-8 h-8 bg-black rounded-full flex items-center justify-center overflow-hidden">
                        <img 
                          src="/cpal.png" 
                          alt="Logo" 
                          className="w-6 h-6 object-contain"
                        />
                      </div>
                    )}
                  </div>

                  {/* Messages */}
                  <div className="space-y-2">
                    {group.msgs.map((msg) => (
                      <motion.div
                        key={msg.id}
                        className={`rounded-2xl px-4 py-3 shadow-lg ${
                          msg.type === 'user'
                            ? 'bg-black border border-white/20' 
                            : msg.error
                            ? 'bg-red-500/20 border border-red-500/30'
                            : 'bg-[#111] border border-[#388bfd]/30'
                        }`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.3 }}
                      >
                        <div className={`text-sm ${msg.type === 'user' ? 'text-white' : 'text-white'} leading-relaxed`}>
                          {msg.text}
                        </div>
                        
                        {/* Timestamp */}
                        <div className={`text-xs mt-2 ${msg.type === 'user' ? 'text-white/60' : 'text-white/60'}`}>
                          {formatTimestamp(msg.timestamp)}
                        </div>

                        {/* Sources */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-[#388bfd]/20">
                            <div className="text-xs text-white/80 mb-1">{t.sources}</div>
                            <div className="space-y-1">
                              {msg.sources.map((source, idx) => (
                                <a
                                  key={idx}
                                  href={source}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center space-x-1 text-xs text-[#388bfd] hover:text-[#5aa3ff] transition-colors"
                                >
                                  <ExternalLink className="w-3 h-3" />
                                  <span className="truncate">{source}</span>
                                </a>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Follow-ups */}
                        {msg.followUps && msg.followUps.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-[#388bfd]/20">
                            <div className="text-xs text-white/80 mb-2">{t.askFollowUp}</div>
                            <div className="space-y-1">
                              {msg.followUps.map((followUp, idx) => (
                                <motion.button
                                  key={idx}
                                  onClick={() => sendMessage(followUp)}
                                  className="block w-full text-left text-xs bg-[#388bfd]/20 hover:bg-[#388bfd]/30 text-white px-3 py-2 rounded-lg transition-colors"
                                  whileHover={{ scale: 1.02 }}
                                  whileTap={{ scale: 0.98 }}
                                >
                                  {followUp}
                                </motion.button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Feedback */}
                        {msg.type === 'bot' && !msg.error && !msg.streaming && (
                          <div className="mt-3 pt-2 border-t border-[#388bfd]/20 flex items-center space-x-2">
                            <motion.button
                              onClick={() => handleFeedback(msg.id, 'up')}
                              disabled={feedbackLoading === msg.id}
                              className={`flex items-center space-x-1 text-xs px-2 py-1 rounded transition-colors ${
                                msg.feedback === 'up'
                                  ? 'bg-green-500/20 text-green-400'
                                  : 'text-white/60 hover:text-green-400 hover:bg-green-500/10'
                              }`}
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                            >
                              <ThumbsUp className="w-3 h-3" />
                              <span>{t.helpful}</span>
                            </motion.button>
                            <motion.button
                              onClick={() => handleFeedback(msg.id, 'down')}
                              disabled={feedbackLoading === msg.id}
                              className={`flex items-center space-x-1 text-xs px-2 py-1 rounded transition-colors ${
                                msg.feedback === 'down'
                                  ? 'bg-red-500/20 text-red-400'
                                  : 'text-white/60 hover:text-red-400 hover:bg-red-500/10'
                              }`}
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                            >
                              <ThumbsDown className="w-3 h-3" />
                              <span>{t.notHelpful}</span>
                            </motion.button>
                          </div>
                        )}
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
            
            {TypingIndicator}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-4 bg-[#111] border-t border-[#388bfd]/20">
            {!isOnline && (
              <motion.div
                className="mb-3 p-2 bg-red-500/20 border border-red-500/30 rounded-lg flex items-center space-x-2"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <AlertTriangle className="w-4 h-4 text-red-400" />
                <span className="text-xs text-red-400">{t.offlineWarning}</span>
              </motion.div>
            )}
            
            <div className="flex items-end space-x-3">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={message}
                  onChange={handleInputChange}
                  onKeyPress={handleKeyPress}
                  placeholder={t.placeholder}
                  disabled={chatState.isTyping || !isOnline}
                  className="w-full bg-black border border-[#388bfd]/30 rounded-2xl px-4 py-3 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-[#388bfd]/40 resize-none min-h-[48px] max-h-32 text-sm"
                  style={{ scrollbarWidth: 'thin', scrollbarColor: '#388bfd #111' }}
                />
                <div className="absolute bottom-2 right-3 text-xs text-white/40">
                  {message.length}/{CHAT_CONFIG.MAX_MESSAGE_LENGTH}
                </div>
              </div>
              <motion.button
                onClick={() => sendMessage()}
                disabled={!message.trim() || message.length > CHAT_CONFIG.MAX_MESSAGE_LENGTH || chatState.isTyping || !isOnline}
                className="w-12 h-12 rounded-full bg-[#388bfd] hover:bg-[#5aa3ff] disabled:bg-[#388bfd]/50 flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-[#388bfd]/40"
                whileHover={{ scale: message.trim() ? 1.1 : 1 }}
                whileTap={{ scale: message.trim() ? 0.9 : 1 }}
                aria-label={t.sendMessage}
                title={t.sendMessage}
              >
                <Send className="w-5 h-5 text-white" />
              </motion.button>
            </div>

            {/* Footer Disclaimer */}
            <div className="mt-3 flex items-center justify-center space-x-1 text-xs text-white/50">
              <Info className="w-3 h-3" />
              <span>{t.disclaimer}</span>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  // --- Clear Confirmation Modal ---
  const clearConfirmModal = (
    <AnimatePresence>
      {showClearConfirm && (
        <motion.div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[10001]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setShowClearConfirm(false)}
        >
          <motion.div
            className="bg-[#111] border border-[#388bfd]/30 rounded-2xl p-6 max-w-sm mx-4 shadow-2xl"
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center space-x-3 mb-4">
              <AlertTriangle className="w-6 h-6 text-red-400" />
              <h3 className="text-white font-semibold">{t.clearConversation}</h3>
            </div>
            <p className="text-white/80 text-sm mb-6">{t.clearConfirmText}</p>
            <div className="flex space-x-3">
              <motion.button
                onClick={() => setShowClearConfirm(false)}
                className="flex-1 px-4 py-2 bg-[#222] hover:bg-[#333] text-white rounded-lg transition-colors text-sm font-medium"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {t.cancel}
              </motion.button>
              <motion.button
                onClick={clearMessages}
                className="flex-1 px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors text-sm font-medium"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                {t.clearAll}
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  if (!isClient) return null;

  return (
    <>
      {chatWindow}
      {floatingButton}
      {clearConfirmModal}
      {showLangMenu && (
        <div 
          className="fixed inset-0 z-[9998]" 
          onClick={() => setShowLangMenu(false)}
        />
      )}
    </>
  );
};

export default CommediaChatbotFloating;