import './Stage5.css';

export default function Stage5({ chairmanDecision }) {
  if (!chairmanDecision || !chairmanDecision.decisions) {
    return null;
  }

  const { model, decisions } = chairmanDecision;

  // Convert decisions object to array if needed
  const decisionsArray = Array.isArray(decisions) 
    ? decisions 
    : Object.entries(decisions).map(([modelName, value]) => ({
        model: modelName,
        chairman_decision: value,
        communication_value: value
      }));

  if (decisionsArray.length === 0) {
    return null;
  }

  return (
    <div className="stage stage5">
      <h3 className="stage-title">Stage 5: Chairman's Final Decisions</h3>
      
      <div className="chairman-model">
        <span className="chairman-label">Chairman:</span>
        <span className="chairman-value">{model.split('/')[1] || model}</span>
      </div>

      <div className="decisions-table">
        <div className="table-header">
          <div className="col-model">Model</div>
          <div className="col-decision">Final MCC Decision</div>
          <div className="col-communication">Communication Value</div>
        </div>
        
        {decisionsArray.map((decision, index) => (
          <div key={index} className="table-row">
            <div className="col-model">
              <span className="model-name">
                {decision.model.split('/')[1] || decision.model}
              </span>
            </div>
            <div className="col-decision">
              <span className="decision-value">{decision.chairman_decision}%</span>
            </div>
            <div className="col-communication">
              <span className="communication-value">{decision.communication_value}%</span>
            </div>
          </div>
        ))}
      </div>

      <div className="decisions-note">
        <strong>Note:</strong> The chairman's strategic decisions will be communicated to LLMs for final acceptance in Stage 5.
      </div>
    </div>
  );
}
