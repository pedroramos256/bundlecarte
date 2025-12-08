import './Stage6.css';

export default function Stage6({ llmFinals, chairmanDecision }) {
  if (!llmFinals) {
    return null;
  }

  // Convert to array if needed and filter out invalid entries
  const finalsArray = (Array.isArray(llmFinals) ? llmFinals : Object.values(llmFinals))
    .filter(f => f && f.model && (f.llm_final_decision !== undefined || f.llm_final_decision_mcc !== undefined));

  if (finalsArray.length === 0) {
    return null;
  }

  // Get chairman's communications from stage5
  const chairmanCommunications = chairmanDecision?.communications || {};

  return (
    <div className="stage stage6">
      <h3 className="stage-title">Stage 6: LLM Final Acceptance</h3>
      
      <div className="finals-grid">
        {finalsArray.map((final, index) => {
          // Handle both field naming conventions
          const finalMCC = final.llm_final_decision ?? final.llm_final_decision_mcc ?? 0;
          const chairmanComm = chairmanCommunications[final.model] ?? 0;
          
          return (
            <div key={index} className="final-card">
              <div className="final-header">
                <span className="final-model">
                  {final.model.split('/')[1] || final.model}
                </span>
              </div>
              
              <div className="final-comparison">
                <div className="comparison-item chairman-comm">
                  <div className="comp-label">Chairman's Communication</div>
                  <div className="comp-value">{chairmanComm}%</div>
                </div>
                
                <div className="arrow-divider">→</div>
                
                <div className="comparison-item llm-final">
                  <div className="comp-label">LLM Final MCC</div>
                  <div className="comp-value highlight">{finalMCC}%</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="finals-note">
        Final MCCs submitted by LLMs after seeing chairman's strategic communication values. Payments will be calculated in Stage 7.
      </div>
    </div>
  );
}
