import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import Stage4 from './Stage4';
import Stage5 from './Stage5';
import Stage6 from './Stage6';
import Stage7 from './Stage7';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  onNewConversation,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  // Check if conversation is in progress based on status
  const isInProgress = conversation?.status === 'processing';
  const currentStage = conversation?.current_stage;

  // Helper to determine if a stage should show loading
  const isStageLoading = (stageNum) => {
    return isInProgress && currentStage !== null && currentStage === stageNum;
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to Bundle Carte</h2>
          <p> Bundle the best models to get great answers </p>
          <button className="start-chat-btn" onClick={onNewConversation}>
            Start new chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the Bundle Carte</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">Bundle Carte</div>

                  {/* Stage 1: Token Budget Quotes */}
                  {(msg.loading?.stage1 || (index === conversation.messages.length - 1 && isStageLoading(1))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Collecting token budget quotes...</span>
                    </div>
                  )}
                  {msg.stage1 && msg.stage1.length > 0 && <Stage1 quotes={msg.stage1} />}

                  {/* Stage 2: LLM Responses */}
                  {(msg.loading?.stage2 || (index === conversation.messages.length - 1 && isStageLoading(2))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>LLMs generating responses...</span>
                    </div>
                  )}
                  {/* Try stage2 first, fall back to stage1 for old conversations */}
                  {(msg.stage2 && (Array.isArray(msg.stage2) ? msg.stage2.length > 0 : msg.stage2)) ? (
                    <Stage2 responses={msg.stage2} />
                  ) : (msg.stage1 && msg.stage1.length > 0 && msg.stage1[0]?.response) ? (
                    <Stage2 responses={msg.stage1} />
                  ) : null}

                  {/* Stage 3: Chairman Evaluation */}
                  {(msg.loading?.stage3 || (index === conversation.messages.length - 1 && isStageLoading(3))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Chairman evaluating and assigning MCCs...</span>
                    </div>
                  )}
                  {msg.stage3 && Object.keys(msg.stage3).length > 0 && <Stage3 chairmanEval={msg.stage3} />}

                  {/* Stage 4: LLM Self-Evaluations */}
                  {(msg.loading?.stage4 || (index === conversation.messages.length - 1 && isStageLoading(4))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Stage 3: LLMs self-evaluating their contributions...</span>
                    </div>
                  )}
                  {msg.stage4 && (Array.isArray(msg.stage4) ? msg.stage4.length > 0 : Object.keys(msg.stage4).length > 0) && <Stage4 selfEvaluations={msg.stage4} />}

                  {/* Stage 5: Chairman Final Decision */}
                  {(msg.loading?.stage5 || (index === conversation.messages.length - 1 && isStageLoading(5))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Chairman making final strategic decisions...</span>
                    </div>
                  )}
                  {msg.stage5 && Object.keys(msg.stage5).length > 0 && <Stage5 chairmanDecision={msg.stage5} />}

                  {/* Stage 6: LLM Final Acceptance */}
                  {(msg.loading?.stage6 || (index === conversation.messages.length - 1 && isStageLoading(6))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>LLMs submitting final MCCs...</span>
                    </div>
                  )}
                  {msg.stage6 && (Array.isArray(msg.stage6) ? msg.stage6.length > 0 : Object.keys(msg.stage6).length > 0) && <Stage6 llmFinals={msg.stage6} chairmanDecision={msg.stage5} />}

                  {/* Stage 7: Final Payments */}
                  {(msg.loading?.stage7 || (index === conversation.messages.length - 1 && isStageLoading(7))) && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Calculating final payments...</span>
                    </div>
                  )}
                  {msg.stage7 && (Array.isArray(msg.stage7) ? msg.stage7.length > 0 : Object.keys(msg.stage7).length > 0) && <Stage7 payments={msg.stage7} />}
                </div>
              )}
            </div>
          ))
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="input-form" onSubmit={handleSubmit}>
        <div className="input-wrapper">
          <textarea
            className="message-input"
            placeholder="Ask your question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={1}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || isLoading}
            aria-label="Send"
          >
            <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
              <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  );
}
