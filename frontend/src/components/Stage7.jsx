import './Stage7.css';

export default function Stage7({ payments }) {
  if (!payments) {
    return null;
  }

  // Convert payments object to array if needed
  const paymentsArray = Array.isArray(payments)
    ? payments
    : payments.per_model_payments 
      ? Object.values(payments.per_model_payments)
      : Object.entries(payments).map(([modelName, data]) => ({
          model: modelName,
          ...data
        }));

  if (paymentsArray.length === 0) {
    return null;
  }

  const totalRevenue = paymentsArray.reduce((sum, p) => sum + (p.payment_amount_usd || p.revenue || 0), 0);
  const totalCost = paymentsArray.reduce((sum, p) => sum + (p.quoted_cost || p.cost || 0), 0);
  const totalProfit = paymentsArray.reduce((sum, p) => sum + (p.profit_usd || p.profit_loss || 0), 0);

  return (
    <div className="stage stage7">
      <h3 className="stage-title">Stage 7: Final Payments</h3>
      
      <div className="payments-table">
        <div className="table-header">
          <div className="col-model">Model</div>
          <div className="col-decision">Decision</div>
          <div className="col-final">Final MCC</div>
          <div className="col-payment">Payment %</div>
          <div className="col-revenue">Revenue</div>
          <div className="col-cost">Cost</div>
          <div className="col-profit">Profit/Loss</div>
        </div>
        
        {paymentsArray.map((payment, index) => (
          <div key={index} className="table-row">
            <div className="col-model">
              <span className="model-name">
                {payment.model.split('/')[1] || payment.model}
              </span>
            </div>
            <div className="col-decision">
              <span className="value">{payment.chairman_decision_mcc ?? payment.chairman_decision ?? 0}%</span>
            </div>
            <div className="col-final">
              <span className="value">{payment.llm_final_decision_mcc ?? payment.llm_final_decision ?? 0}%</span>
            </div>
            <div className="col-payment">
              <span className="value payment-highlight">{(payment.chairman_pays_mcc ?? payment.payment_mcc ?? 0)?.toFixed?.(1) || 0}%</span>
            </div>
            <div className="col-revenue">
              <span className="value">${(payment.payment_amount_usd ?? payment.revenue ?? 0).toFixed?.(4) || '0.0000'}</span>
            </div>
            <div className="col-cost">
              <span className="value">${(payment.quoted_cost ?? payment.cost ?? 0).toFixed?.(4) || '0.0000'}</span>
            </div>
            <div className="col-profit">
              <span className={`value profit ${(payment.profit_usd ?? payment.profit_loss ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                {(payment.profit_usd ?? payment.profit_loss ?? 0) >= 0 ? '+' : ''}${(payment.profit_usd ?? payment.profit_loss ?? 0).toFixed?.(4) || '0.0000'}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="totals-section">
        <div className="total-item">
          <span className="total-label">Total Revenue:</span>
          <span className="total-value">${totalRevenue?.toFixed(4) || '0.0000'}</span>
        </div>
        <div className="total-item">
          <span className="total-label">Total Cost:</span>
          <span className="total-value">${totalCost?.toFixed(4) || '0.0000'}</span>
        </div>
        <div className="total-item">
          <span className="total-label">Total Profit:</span>
          <span className={`total-value ${totalProfit >= 0 ? 'positive' : 'negative'}`}>
            {totalProfit >= 0 ? '+' : ''}${totalProfit?.toFixed(4) || '0.0000'}
          </span>
        </div>
      </div>

      <div className="payment-rules">
        <strong>Payment Rules:</strong>
        <ul>
          <li>If chairman_decision &lt; llm_final: Chairman pays llm_final + {5}%, LLM receives chairman_decision - {5}%</li>
          <li>If chairman_decision ≥ llm_final: Both receive average (chairman_decision + llm_final) / 2</li>
        </ul>
      </div>
    </div>
  );
}
