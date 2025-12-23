import { useState } from 'react';
import './Stage7.css';

export default function Stage7({ payments }) {
  const [isOpen, setIsOpen] = useState(false);
  
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

  const totalLLMPayment = paymentsArray.reduce((sum, p) => sum + (p.llm_receives_mcc || 0), 0);
  const totalChairmanPayment = paymentsArray.reduce((sum, p) => sum + (p.chairman_pays_mcc || 0), 0);
  const totalLLMDollars = paymentsArray.reduce((sum, p) => sum + (p.payment_amount_usd || 0), 0);
  const totalChairmanDollars = paymentsArray.reduce((sum, p) => sum + (p.chairman_payment_usd || 0), 0);
  
  // Calculate chairman dollars from the payments data
  const chairmanEarnings = payments.chairman_earnings_usd || 0;

  return (
    <div className="stage stage7">
      <div className="stage-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <h3 className="stage-title">
          <span className="toggle-icon">{isOpen ? '▼ ' : '▶ '}</span>
          Payments
        </h3>
      </div>
      
      {isOpen && (
        <>
        <div className="payments-table">
        <div className="table-header">
          <div className="col-model">Model</div>
          <div className="col-decision">Chairman Decision</div>
          <div className="col-final">LLM Decision</div>
          <div className="col-chairman-payment">Chairman Payment</div>
          <div className="col-llm-payment">LLM Received</div>
          <div className="col-chairman-dollars">Chairman $</div>
          <div className="col-llm-dollars">LLM $</div>
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
            <div className="col-chairman-payment">
              <span className="value">{(payment.chairman_pays_mcc ?? payment.payment_mcc ?? 0)?.toFixed?.(1) || 0}%</span>
            </div>
            <div className="col-llm-payment">
              <span className="value payment-highlight">{(payment.llm_receives_mcc ?? 0)?.toFixed?.(1) || 0}%</span>
            </div>
            <div className="col-chairman-dollars">
              <span className="value">${(payment.chairman_payment_usd ?? 0).toFixed?.(4) || '0.0000'}</span>
            </div>
            <div className="col-llm-dollars">
              <span className="value">${(payment.payment_amount_usd ?? payment.revenue ?? 0).toFixed?.(4) || '0.0000'}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="totals-section">
        <div className="total-item">
          <span className="total-label">Total LLM Received:</span>
          <span className="total-value">{totalLLMPayment?.toFixed(1) || '0.0'}%</span>
        </div>
        <div className="total-item">
          <span className="total-label">Total Chairman Payment:</span>
          <span className="total-value">{totalChairmanPayment?.toFixed(1) || '0.0'}%</span>
        </div>
        <div className="total-item">
          <span className="total-label">Total LLM $ Received:</span>
          <span className="total-value">${totalLLMDollars?.toFixed(4) || '0.0000'}</span>
        </div>
        <div className="total-item">
          <span className="total-label">Total Chairman $ Paid:</span>
          <span className="total-value">${totalChairmanDollars?.toFixed(4) || '0.0000'}</span>
        </div>
        <div className="total-item">
          <span className="total-label">Chairman Earnings:</span>
          <span className={`total-value ${chairmanEarnings >= 0 ? 'positive' : 'negative'}`}>
            {chairmanEarnings >= 0 ? '+' : ''}${chairmanEarnings?.toFixed(4) || '0.0000'}
          </span>
        </div>
      </div>

      <div className="payment-rules">
        <strong>Payment Rules:</strong>
        <ul>
          <li>If chairman_decision &lt; llm_final: Chairman pays llm_final + penalty (20% of difference), LLM receives chairman_decision - penalty</li>
          <li>If chairman_decision ≥ llm_final: Both receive average (chairman_decision + llm_final) / 2</li>
        </ul>
      </div>
      </>
      )}
    </div>
  );
}
