import { useState } from 'react';
import './Stage1.css';

export default function Stage1({ quotes }) {
  const [isOpen, setIsOpen] = useState(false);
  
  if (!quotes || quotes.length === 0) {
    return null;
  }

  // Check if the data has the expected structure
  const hasValidStructure = quotes.every(q => 
    q.quoted_tokens !== undefined && 
    q.cost_per_million !== undefined && 
    q.estimated_cost !== undefined
  );

  if (!hasValidStructure) {
    // Old format detected - don't render anything, let Stage2 handle it
    return null;
  }

  // Show only top 10 models
  const displayQuotes = quotes.slice(0, 10);
  const totalEstimatedCost = displayQuotes.reduce((sum, q) => sum + q.estimated_cost, 0);
  const selectedQuotes = displayQuotes.filter(q => q.selected);
  const selectedCost = selectedQuotes.reduce((sum, q) => sum + q.estimated_cost, 0);

  return (
    <div className="stage stage1">
      <div className="stage-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <h3 className="stage-title">
          <span className="toggle-icon">{isOpen ? '▼ ' : '▶ '}</span>
          Token Auction - Top 10 Models Bid
        </h3>
        <p className="stage-subtitle">3 cheapest bidders selected for the council</p>
      </div>
      
      {isOpen && (
        <>
        <div className="quotes-grid">
        {displayQuotes.map((quote, index) => (
          <div key={index} className={`quote-card ${quote.selected ? 'selected' : 'not-selected'}`}>
            {quote.selected && <div className="selected-badge">✓ SELECTED</div>}
            <div className="quote-model">
              {quote.model.split('/')[1] || quote.model}
            </div>
            <div className="quote-details">
              <div className="quote-row">
                <span className="quote-label">Quoted Tokens:</span>
                <span className="quote-value">{quote.quoted_tokens.toLocaleString()}</span>
              </div>
              <div className="quote-row">
                <span className="quote-label">Cost per M:</span>
                <span className="quote-value">${quote.cost_per_million.toFixed(2)}</span>
              </div>
              <div className="quote-row">
                <span className="quote-label">Output Cost per M:</span>
                <span className="quote-value">${(quote.output_cost_per_million || quote.cost_per_million).toFixed(2)}</span>
              </div>
              <div className="quote-row">
                <span className="quote-label">Est. Cost:</span>
                <span className="quote-value cost-highlight">
                  ${quote.estimated_cost.toFixed(4)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="cost-summary">
        <div className="cost-item selected-summary">
          <span className="cost-label">Selected 3 Models Cost:</span>
          <span className="cost-value">${selectedCost.toFixed(4)}</span>
        </div>
      </div>
      </>
      )}
    </div>
  );
}
