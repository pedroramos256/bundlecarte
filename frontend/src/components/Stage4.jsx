import { useState } from 'react';
import './Stage4.css';

export default function Stage4({ selfEvaluations }) {
  const [isOpen, setIsOpen] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState(null);

  if (!selfEvaluations || selfEvaluations.length === 0) {
    return null;
  }

  const toggleExpand = (index) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  return (
    <div className="stage stage4">
      <div className="stage-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <h3 className="stage-title">
          <span className="toggle-icon">{isOpen ? '▼ ' : '▶ '}</span>
           Self-Evaluations
        </h3>
      </div>
      
      {isOpen && (
        <>
        <div className="evaluations-list">
        {selfEvaluations.map((evaluation, index) => (
          <div key={index} className="evaluation-card">
            <div 
              className="evaluation-header"
              onClick={() => toggleExpand(index)}
            >
              <div className="eval-model">
                {evaluation.model.split('/')[1] || evaluation.model}
              </div>
              <div className="eval-mccs">
                <div className="mcc-badge chairman">
                  <span className="mcc-label">Chairman:</span>
                  <span className="mcc-val">{evaluation.chairman_initial_mcc}%</span>
                </div>
                <span className="arrow">→</span>
                <div className="mcc-badge self">
                  <span className="mcc-label">Self:</span>
                  <span className="mcc-val">{evaluation.self_mcc}%</span>
                </div>
              </div>
              <button className="expand-btn">
                {expandedIndex === index ? '−' : '+'}
              </button>
            </div>
            
            {expandedIndex === index && (
              <div className="evaluation-content">
                <div className="arguments-section">
                  <h5 className="content-heading">Arguments</h5>
                  <p className="arguments-text">{evaluation.arguments}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      </>
      )}
    </div>
  );
}
