import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [resumedConversations, setResumedConversations] = useState(new Set());

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  // Auto-resume in-progress conversations
  useEffect(() => {
    if (currentConversation && 
        currentConversation.status === 'processing' && 
        !isLoading &&
        !resumedConversations.has(currentConversation.id)) {
      // Mark as resumed to prevent re-triggering
      setResumedConversations(prev => new Set([...prev, currentConversation.id]));
      // Automatically resume the conversation
      handleSendMessage(''); // Empty message to trigger resume
    }
  }, [currentConversation?.id, currentConversation?.status]);

  // Handle page visibility changes (screen sleep/wake)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (!document.hidden && currentConversationId) {
        // Page became visible - reload conversation to get latest state
        console.log('Page visible again, reloading conversation...');
        loadConversation(currentConversationId);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [currentConversationId]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, message_count: 0 },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
  };

  const handleSendMessage = async (content) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Check if this is a resume operation (empty content means resume)
      const isResume = content === '';
      
      // Optimistically add user message to UI (only for new messages, not resume)
      if (!isResume) {
        const userMessage = { role: 'user', content };
        setCurrentConversation((prev) => ({
          ...prev,
          messages: [...prev.messages, userMessage],
        }));
      }

      // Create a partial assistant message that will be updated progressively
      // (or get existing one if resuming)
      let assistantMessage;
      const lastMessage = currentConversation?.messages[currentConversation.messages.length - 1];
      
      if (isResume && lastMessage?.role === 'assistant') {
        // Resuming - use existing assistant message
        assistantMessage = lastMessage;
      } else {
        // New message - create new assistant message
        assistantMessage = {
          role: 'assistant',
          stage1: null, // Token budget quotes
          stage2: null, // LLM responses
          stage3: null, // Chairman evaluation
          stage4: null, // LLM self-evaluations
          stage5: null, // Chairman final decision
          stage6: null, // LLM final acceptance
          stage7: null, // Final payments
          metadata: null,
          loading: {
            stage1: false,
            stage2: false,
            stage3: false,
            stage4: false,
            stage5: false,
            stage6: false,
            stage7: false,
          },
        };

        // Add the partial assistant message
        setCurrentConversation((prev) => ({
          ...prev,
          messages: [...prev.messages, assistantMessage],
        }));
      }

      // Send message with streaming
      await api.sendMessageStream(currentConversationId, content, (eventType, event) => {
        switch (eventType) {
          case 'stage0_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage1 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage0_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.stage1 = event.data;
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage1 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage1_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage2 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage1_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.stage2 = event.data;
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage2 = false;
                lastMsg.loading.stage1 = false; // Also clear stage1 loading
              }
              return { ...prev, messages };
            });
            break;

          case 'stage2_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage3 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage2_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                // Transform chairman evaluation data structure
                const evalData = event.data;
                const initialMccsArray = Object.entries(evalData.chairman_mccs || {}).map(([model, mcc]) => ({
                  model,
                  mcc
                }));
                
                lastMsg.stage3 = {
                  model: evalData.model,
                  aggregated_answer: evalData.aggregated_answer,
                  initial_mccs: initialMccsArray
                };
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage3 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage3_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage4 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage3_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                lastMsg.stage4 = event.data;
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage4 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage4_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage5 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage4_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                // Transform chairman decision data structure
                const decisionData = event.data;
                const decisionsArray = Object.entries(decisionData.decisions || {}).map(([model, decision]) => ({
                  model,
                  chairman_decision: decision,
                  communication_value: decisionData.communications?.[model] || decision
                }));
                
                lastMsg.stage5 = {
                  model: decisionData.model,
                  decisions: decisionsArray,
                  communications: decisionData.communications
                };
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage5 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage5_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage6 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage5_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                // Add chairman communication values from stage5 data
                const llmFinalsArray = event.data.map(llmFinal => ({
                  model: llmFinal.model,
                  chairman_communication: lastMsg.stage5?.decisions?.find(d => d.model === llmFinal.model)?.communication_value || 0,
                  llm_final_decision: llmFinal.llm_final_decision
                }));
                
                lastMsg.stage6 = llmFinalsArray;
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage6 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage6_start':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage7 = true;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage6_complete':
            setCurrentConversation((prev) => {
              const messages = [...prev.messages];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg && lastMsg.role === 'assistant') {
                // Store the complete payment data structure
                lastMsg.stage7 = event.data;
                if (!lastMsg.loading) lastMsg.loading = {};
                lastMsg.loading.stage7 = false;
              }
              return { ...prev, messages };
            });
            break;

          case 'title_complete':
            // Reload conversations to get updated title
            loadConversations();
            break;

          case 'complete':
            // Stream complete, reload conversations list
            loadConversations();
            setIsLoading(false);
            break;

          case 'error':
            console.error('Stream error:', event.message);
            setIsLoading(false);
            break;

          default:
            console.log('Unknown event type:', eventType);
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      
      // If error occurred during streaming, reload conversation to get actual state
      if (currentConversationId) {
        console.log('Stream interrupted, reloading conversation state...');
        setTimeout(() => loadConversation(currentConversationId), 1000);
      }
      
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        onNewConversation={handleNewConversation}
        isLoading={isLoading}
      />
    </div>
  );
}

export default App;
