import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage3.css';

export default function Stage3({ chairmanEval }) {
  const [isOpen, setIsOpen] = useState(true); // Open by default
  
  if (!chairmanEval) {
    return null;
  }

  const { aggregated_answer, initial_mccs, chairman_mccs, model, response } = chairmanEval;

  // Handle old format (just has 'response' field)
  if (response && !aggregated_answer) {
    return (
      <div className="stage stage3">
        <h3 className="stage-title">Chairman's Aggregated Answer</h3>
        
        {model && (
          <div className="chairman-model">
            <span className="chairman-label">Chairman:</span>
            <span className="chairman-value">{model.split('/')[1] || model}</span>
          </div>
        )}

        <div className="aggregated-section">
          <div className="aggregated-answer">
            <div className="markdown-content">
              <ReactMarkdown>{response}</ReactMarkdown>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Handle new format with chairman_mccs dictionary
  if (aggregated_answer && chairman_mccs) {
    return (
      <div className="stage stage3">
        <h3 className="stage-title">Chairman's Answer</h3>
        
        <div className="chairman-model">
          <span className="chairman-label">Chairman:</span>
          <span className="chairman-value">{model ? (model.split('/')[1] || model) : 'Chairman'}</span>
        </div>

        <div className="aggregated-section">
          <div className="aggregated-answer">
            <div className="markdown-content">
              <ReactMarkdown>{aggregated_answer}</ReactMarkdown>
            </div>
          </div>
        </div>

        <div className="mcc-section">
          <h4 className="section-heading">Marginal Contributions</h4>
          <div className="mcc-bars">
            {Object.entries(chairman_mccs).map(([mName, score]) => (
              <div key={mName} className="mcc-item">
                <div className="mcc-header">
                  <span className="mcc-model">{mName.split('/').pop()}</span>
                  <span className="mcc-percentage">{score}%</span>
                </div>
                <div className="mcc-bar-container">
                  <div 
                    className="mcc-bar" 
                    style={{ 
                      width: `${score}%`,
                      height: '100%',
                      background: '#002fa7',
                      borderRadius: '4px'
                    }} 
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Check if we have the expected new data structure
  if (!aggregated_answer || !initial_mccs || !Array.isArray(initial_mccs)) {
    return null;
  }

  return (
    <div className="stage stage3">
      <div className="stage-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <h3 className="stage-title">
          <span className="toggle-icon">{isOpen ? '▼ ' : '▶ '}</span>
          Chairman Evaluation
        </h3>
      </div>
      
      {isOpen && (
        <>
        <div className="chairman-model">
        <span className="chairman-label">Chairman:</span>
        <span className="chairman-value">{model.split('/')[1] || model}</span>
      </div>

      <div className="aggregated-section">
        <h4 className="section-heading">Aggregated Answer</h4>
        <div className="aggregated-answer markdown-content">
          <ReactMarkdown>{aggregated_answer}</ReactMarkdown>
        </div>
      </div>

      <div className="mcc-section">
        <h4 className="section-heading">Marginal Contributions</h4>
        <div className="mcc-bars">
          {initial_mccs.map((item, index) => (
            <div key={index} className="mcc-item">
              <div className="mcc-header">
                <span className="mcc-model">{item.model.split('/')[1] || item.model}</span>
                <span className="mcc-percentage">{item.mcc}%</span>
              </div>
              <div className="mcc-bar-container">
                <div 
                  className="mcc-bar-fill" 
                  style={{ width: `${item.mcc}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        
        <div className="mcc-total">
          Total: {initial_mccs.reduce((sum, item) => sum + item.mcc, 0)}%
        </div>
      </div>
      </>
      )}
    </div>
  );
}
