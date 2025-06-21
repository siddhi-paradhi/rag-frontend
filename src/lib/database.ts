import { supabase, Conversation, Message } from './supabase'

export class DatabaseService {
  // Get user's conversations
  static async getConversations(userId: string): Promise<Conversation[]> {
    const { data, error } = await supabase
      .from('conversations')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })
    
    if (error) throw error
    return data || []
  }

  // Create new conversation
  static async createConversation(userId: string, title: string): Promise<Conversation> {
    const { data, error } = await supabase
      .from('conversations')
      .insert([{ user_id: userId, title }])
      .select()
      .single()
    
    if (error) throw error
    return data
  }

  // Get messages for a conversation
  static async getMessages(conversationId: string): Promise<Message[]> {
    const { data, error } = await supabase
      .from('messages')
      .select('*')
      .eq('conversation_id', conversationId)
      .order('created_at', { ascending: true })
    
    if (error) throw error
    return data || []
  }

  // Add message to conversation
  static async addMessage(
    conversationId: string,
    type: 'user' | 'assistant',
    content: string,
    sources?: string[],
    followUps?: string[]
  ): Promise<Message> {
    const { data, error } = await supabase
      .from('messages')
      .insert([{
        conversation_id: conversationId,
        type,
        content,
        sources: sources || [],
        follow_ups: followUps || []
      }])
      .select()
      .single()
    
    if (error) throw error

    // Update conversation's updated_at
    await supabase
      .from('conversations')
      .update({ updated_at: new Date().toISOString() })
      .eq('id', conversationId)
    
    return data
  }

  // Update conversation title
  static async updateConversationTitle(conversationId: string, title: string): Promise<void> {
    const { error } = await supabase
      .from('conversations')
      .update({ title, updated_at: new Date().toISOString() })
      .eq('id', conversationId)
    
    if (error) throw error
  }

  // Delete conversation
  static async deleteConversation(conversationId: string): Promise<void> {
    const { error } = await supabase
      .from('conversations')
      .delete()
      .eq('id', conversationId)
    
    if (error) throw error
  }
}