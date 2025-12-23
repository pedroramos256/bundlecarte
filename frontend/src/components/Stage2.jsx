import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage2.css';

export default function Stage2({ responses }) {
  const [activeTab, setActiveTab] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  if (!responses || responses.length === 0) {
    return null;
  }

  // Check if responses have the required 'response' field
  const hasValidResponses = responses.every(r => r.response !== undefined);
  if (!hasValidResponses) {
    return null;
  }

  return (
    <div className="stage stage2">
      <div className="stage-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <h3 className="stage-title">
          <span className="toggle-icon">{isOpen ? '▼' : '▶'}</span>
          LLM Responses
        </h3>
      </div>
      
      {isOpen && (
        <>
        <div className="tabs">
        {responses.map((resp, index) => (
          <button
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {resp.model.split('/')[1] || resp.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">{responses[activeTab].model}</div>
        <div className="response-text markdown-content">
          <ReactMarkdown>{responses[activeTab].response}</ReactMarkdown>
        </div>
      </div>
      </>
      )}
    </div>
  );
}
