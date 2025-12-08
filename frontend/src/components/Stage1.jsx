import './Stage1.css';

export default function Stage1({ quotes }) {
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

  const totalEstimatedCost = quotes.reduce((sum, q) => sum + q.estimated_cost, 0);

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Token Budget Quotes</h3>
      
      <div className="quotes-grid">
        {quotes.map((quote, index) => (
          <div key={index} className="quote-card">
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
                <span className="quote-label">Estimated Cost:</span>
                <span className="quote-value cost-highlight">
                  ${quote.estimated_cost.toFixed(4)}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="total-cost">
        <span className="total-label">Total Estimated Cost:</span>
        <span className="total-value">${totalEstimatedCost.toFixed(4)}</span>
      </div>
    </div>
  );
}
