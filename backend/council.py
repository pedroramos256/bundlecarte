"""LLM Council orchestration with token auction mechanism."""

from typing import List, Dict, Any, Tuple, Optional
import re
from .openrouter import query_models_parallel, query_model
from .config import COUNCIL_MODELS, CHAIRMAN_MODEL, MODEL_COSTS, NEGOTIATION_PENALTY_T


# ============================================================================
# NEW AUCTION MECHANISM - STAGE 1: TOKEN BUDGET QUOTING
# ============================================================================

async def stage0_collect_quotes(user_query: str) -> List[Dict[str, Any]]:
    """
    Stage 0: Each LLM quotes how many tokens they want to use.
    
    LLMs estimate optimal token count based on prompt complexity and their cost,
    knowing they'll be paid based on Marginal Churn Contribution.
    
    Args:
        user_query: The user's question
        
    Returns:
        List of dicts with keys: 'model', 'cost_per_million', 'quoted_tokens', 'estimated_cost'
    """
    print(f"[STAGE0] Starting token quote collection for query: {user_query[:100]}...")
    n_models = len(COUNCIL_MODELS)
    print(f"[STAGE0] Number of models: {n_models}")
    print(f"[STAGE0] Models: {COUNCIL_MODELS}")
    
    # Build quote request messages for each model
    quote_requests = {}
    for model in COUNCIL_MODELS:
        cost = MODEL_COSTS.get(model, 10.0)  # Default to $10 if not found
        
        prompt = f"""You are bidding on how many tokens to use for answering a question.

USER QUESTION:
{user_query}

Your cost: ${cost} per million tokens
Competition: {n_models-1} other LLMs are also bidding
Payment formula: (Your MCC% / 100) × Total_Quote_Sum - Your_Cost

IMPORTANT: You MUST respond with ONLY a number between 500-16000. Nothing else.

Guidelines:
- Simple math/factual questions: 500-1000 tokens
- Moderate explanations: 1000-2000 tokens  
- Complex analysis/essays: 2000-8000 tokens
- Very detailed research: 4000-16000 tokens

Balance quality vs cost. More tokens = better answer = higher MCC, but also higher cost.

Respond with ONLY the number (e.g., 800):"""

        quote_requests[model] = [{"role": "user", "content": prompt}]
    
    print(f"[STAGE0] Built {len(quote_requests)} quote requests")
    
    # Query all models in parallel
    responses = {}
    for model, messages in quote_requests.items():
        print(f"[STAGE0] Querying model: {model}")
        response = await query_model(model, messages)
        print(f"[STAGE0] Got response from {model}: {response is not None}")
        if response:
            print(f"[STAGE0] Response content: {response.get('content', '')[:200]}")
        else:
            print(f"[STAGE0] Response was None!")
        responses[model] = response
    
    # Parse responses and extract token counts
    print(f"[STAGE0] Parsing responses...")
    stage0_results = []
    for model in COUNCIL_MODELS:
        response = responses.get(model)
        cost_per_million = MODEL_COSTS.get(model, 10.0)
        
        if response is None:
            # Failed to get response, use default
            print(f"[STAGE0] {model}: No response, using default 1000 tokens")
            quoted_tokens = 1000  # Default token count - reasonable middle ground
        else:
            # Extract integer from response
            content = response.get('content', '').strip()
            quoted_tokens = _parse_token_count(content)
            print(f"[STAGE0] {model}: Parsed {quoted_tokens} tokens from response")
        
        # Calculate estimated cost
        estimated_cost = (quoted_tokens / 1_000_000) * cost_per_million
        
        stage0_results.append({
            "model": model,
            "cost_per_million": cost_per_million,
            "quoted_tokens": quoted_tokens,
            "estimated_cost": estimated_cost,
            "raw_response": response.get('content', '') if response else None
        })
    
    print(f"[STAGE0] Completed. Total quotes: {len(stage0_results)}")
    print(f"[STAGE0] Total estimated cost: ${sum(r['estimated_cost'] for r in stage0_results):.4f}")
    return stage0_results


def _parse_token_count(text: str) -> int:
    """
    Extract token count from LLM response.
    Handles various formats and falls back to default.
    
    Args:
        text: Response text from LLM
        
    Returns:
        Integer token count (default 1500 if parsing fails)
    """
    if not text:
        return 1500
    
    # Remove common formatting
    text = text.strip().replace(',', '').replace('tokens', '').replace('token', '')
    
    # Try to find a number
    numbers = re.findall(r'\d+', text)
    
    if numbers:
        # Take the first number found
        token_count = int(numbers[0])
        # Sanity check: reasonable range (50 to 16000 tokens)
        if 50 <= token_count <= 16000:
            return token_count
        # If out of range but a number was given, try to salvage it
        if token_count < 50:
            return 500  # Too small, use minimum reasonable
        if token_count > 16000:
            return 8000  # Too large, cap it
        return 1500
    
    # No number found, use default
    return 1500


# ============================================================================
# ORIGINAL 3-STAGE COUNCIL (Keep for backward compatibility)
# ============================================================================

async def stage1_collect_responses(user_query: str, max_tokens_per_model: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models with MCC-aware prompting.
    
    Each LLM is informed they'll be paid based on Marginal Churn Contribution,
    encouraging them to provide unique value (stop game dynamics).

    Args:
        user_query: The user's question
        max_tokens_per_model: Optional dict mapping model to max_tokens limit (from Stage 0 quotes)

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    n_models = len(COUNCIL_MODELS)
    
    # Build responses with token budget awareness for each model
    responses_list = []
    
    for model in COUNCIL_MODELS:
        max_tokens = None
        token_budget_note = ""
        
        if max_tokens_per_model and model in max_tokens_per_model:
            max_tokens = max_tokens_per_model[model]
            token_budget_note = f"\n\nYou have a token budget of {max_tokens} tokens for your answer. Be concise but comprehensive given this budget. If {max_tokens} < 1000, focus on the most critical points. If {max_tokens} >= 2000, you can provide more detailed analysis."
        
        # Build the MCC-aware prompt for each model
        prompt = f"""Answer to the following user prompt:
<prompt>
{user_query}
</prompt>

Take into account that other {n_models - 1} LLMs are answering as well and you will be paid based on your Marginal Churn Contribution (probability of the user preferring your quote and answer instead of the aggregate quote and aggregate answer). 

So you should both give a complete answer and bring to the table value that the other LLMs may not bring. Think of it as the stop game, information no other LLM mentions will be more valuable than what everyone else mentions. 

IMPORTANT: Respond with just your answer to the user prompt
{token_budget_note}"""

        messages = [{"role": "user", "content": prompt}]
        responses_list.append((model, messages, max_tokens))
    
    # Query all models in parallel with token limits if provided
    responses = {}
    for model, messages, max_tokens in responses_list:
        response = await query_model(model, messages, max_tokens=max_tokens)
        responses[model] = response

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return stage1_results


async def stage2_evaluate_mccs(
    user_query: str,
    stage0_quotes: List[Dict[str, Any]],
    stage1_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 2: Chairman aggregates answers and evaluates Marginal Churn Contribution (MCC).
    
    Chairman creates aggregated answer and assigns MCC scores to each LLM.
    MCC scores must sum to <= 100.

    Args:
        user_query: The original user query
        stage0_quotes: Token quotes from Stage 0
        stage1_results: Individual responses from Stage 1

    Returns:
        Dict with 'aggregated_answer', 'chairman_mccs', 'model', 'raw_response'
    """
    # Calculate total quote sum for payment context
    quote_sum = sum(q["estimated_cost"] for q in stage0_quotes)
    
    # Build the answers text with numbering
    answers_text = "\n\n".join([
        f"LLM {i+1}:\n{result['response']}\n------------\n"
        for i, result in enumerate(stage1_results)
    ])
    
    # Build chairman evaluation prompt
    chairman_prompt = f"""You are the chairman of an LLM council evaluating {len(stage1_results)} answers.

USER QUESTION:
{user_query}

LLM ANSWERS:
{answers_text}

Your tasks:
1. Create a comprehensive aggregated answer combining the best insights
2. Evaluate each LLM's Marginal Churn Contribution (MCC) = probability users would prefer an LLM individual answer over your aggregate

CRITICAL MCC RULES:
- Higher MCC = more unique value, better quality, key insights users would miss in aggregate
- Lower MCC = redundant, lower quality, or well-covered in aggregate
- You earn 100% - sum(MCCs), so be fair but strategic
- Typical distribution: excellent answers 35-70%, good 15-35%, weak 5-15%

Consider: accuracy, clarity, completeness, unique contributions, user preference likelihood

Answer in this EXACT JSON format:
{{
  "aggregated_answer": "your comprehensive answer",
  "MCC_LLM_1": number_0_to_100,
  "MCC_LLM_2": number_0_to_100,
  "MCC_LLM_3": number_0_to_100,
  "MCC_LLM_4": number_0_to_100
}}

IMPORTANT: Return ONLY valid JSON, nothing else."""

    messages = [{"role": "user", "content": chairman_prompt}]
    
    # Query chairman model with extended timeout for comprehensive answer
    response = await query_model(CHAIRMAN_MODEL, messages, max_tokens=8192, timeout=240.0)
    
    if response is None:
        # Fallback if chairman fails
        return {
            "model": CHAIRMAN_MODEL,
            "aggregated_answer": "Error: Unable to generate aggregated answer.",
            "chairman_mccs": {},
            "raw_response": None
        }
    
    raw_response = response.get('content', '')
    
    # Parse JSON response
    import json
    try:
        parsed = json.loads(raw_response)
        aggregated_answer = parsed.get("aggregated_answer", "")
        
        # Extract MCC values for each LLM
        chairman_mccs = {}
        for i, result in enumerate(stage1_results):
            mcc_key = f"MCC_LLM_{i+1}"
            chairman_mccs[result['model']] = parsed.get(mcc_key, 0)
        
        return {
            "model": CHAIRMAN_MODEL,
            "aggregated_answer": aggregated_answer,
            "chairman_mccs": chairman_mccs,
            "raw_response": raw_response
        }
    except json.JSONDecodeError:
        # Fallback parsing if JSON is malformed
        return {
            "model": CHAIRMAN_MODEL,
            "aggregated_answer": raw_response,
            "chairman_mccs": {result['model']: 0 for result in stage1_results},
            "raw_response": raw_response
        }


async def stage3_llm_self_evaluation(
    user_query: str,
    stage0_quotes: List[Dict[str, Any]],
    stage1_results: List[Dict[str, Any]],
    stage2_chairman_eval: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Stage 3: Each LLM self-evaluates their MCC and argues for their unique value.
    
    LLMs see the chairman's evaluation and provide arguments for their contribution.

    Args:
        user_query: The original user query
        stage0_quotes: Token quotes from Stage 0
        stage1_results: Individual responses from Stage 1
        stage2_chairman_eval: Chairman's aggregated answer and MCC evaluations

    Returns:
        List of dicts with 'model', 'arguments', 'self_mcc''
    """
    n_models = len(stage1_results)
    quote_sum = sum(q["estimated_cost"] for q in stage0_quotes)
    aggregated_answer = stage2_chairman_eval.get("aggregated_answer", "")
    chairman_mccs = stage2_chairman_eval.get("chairman_mccs", {})
    
    # Prepare self-evaluation prompts for each LLM
    self_eval_tasks = []
    
    for i, result in enumerate(stage1_results):
        model = result['model']
        answer = result['response']
        chairman_mcc = chairman_mccs.get(model, 0)
        
        # Get quote for this model
        quote = next((q for q in stage0_quotes if q['model'] == model), None)
        quoted_cost = quote['estimated_cost'] if quote else 0
        
        # Build list of other answers
        other_answers = "\n\n".join([
            f"LLM {j+1}:\n{r['response']}\n------------\n"
            for j, r in enumerate(stage1_results) if r['model'] != model
        ])
        
        prompt = f"""USER QUESTION:
{user_query}

YOUR ANSWER:
{answer}

OTHER {n_models - 1} LLM ANSWERS:
{other_answers}

AGGREGATED ANSWER:
{aggregated_answer}

SITUATION:
- Chairman's initial MCC evaluation of you: {chairman_mcc}%
- Your cost: ${quoted_cost:.4f}
- Total pot: ${quote_sum:.4f}

Now you must self-evaluate your MCC (Marginal Churn Contribution = probability users prefer YOUR answer over the aggregate).

STRATEGIC PAYMENT RULES:
- If your self-MCC > chairman's MCC: You'll receive (chairman_MCC - {NEGOTIATION_PENALTY_T})% (PENALTY for overestimating!)
- If your self-MCC ≤ chairman's MCC: You'll receive (chairman_MCC + self_MCC)/2 (REWARD for being reasonable)
- Your payment = (final_MCC% / 100) × ${quote_sum:.4f} - ${quoted_cost:.4f}

Be strategic! Argue for your unique value, but consider:
- If chairman gave you {chairman_mcc}%, claiming higher risks penalty, but this is an anchor value part of a negotiation, you will still receive a response from the chairman and then you take the final decision
- Claiming equal or slightly lower gets you the average
- What unique insights do you provide that other LLMs lack?

Answer in this EXACT JSON format:
{{
  "arguments": "specific unique value your answer provides that other LLMs don't",
  "MCC": number_0_to_100
}}

IMPORTANT: Return ONLY valid JSON, nothing else."""

        self_eval_tasks.append((model, prompt))
    
    # Query all models in parallel
    self_eval_results = []
    for model, prompt in self_eval_tasks:
        messages = [{"role": "user", "content": prompt}]
        response = await query_model(model, messages, max_tokens=8192)
        
        if response is None:
            self_eval_results.append({
                "model": model,
                "arguments": "Failed to generate self-evaluation",
                "self_mcc": chairman_mccs.get(model, 0),
            })
            continue
        
        raw_response = response.get('content', '')
        
        # Parse JSON response
        import json
        try:
            parsed = json.loads(raw_response)
            self_eval_results.append({
                "model": model,
                "chairman_initial_mcc": chairman_mccs.get(model, 0),
                "arguments": parsed.get("arguments", ""),
                "self_mcc": parsed.get("MCC", 0)
            })
        except json.JSONDecodeError:
            # Try to extract JSON from wrapped response
            try:
                # Look for JSON object pattern
                json_match = re.search(r'\{[^{}]*"MCC"[^{}]*\}', raw_response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    self_eval_results.append({
                        "model": model,
                        "chairman_initial_mcc": chairman_mccs.get(model, 0),
                        "arguments": parsed.get("arguments", raw_response[:200]),
                        "self_mcc": parsed.get("MCC", chairman_mccs.get(model, 0))
                    })
                else:
                    # Try to extract just MCC number
                    mcc_match = re.search(r'["\']?MCC["\']?\s*:\s*(\d+)', raw_response)
                    if mcc_match:
                        mcc_value = int(mcc_match.group(1))
                        self_eval_results.append({
                            "model": model,
                            "chairman_initial_mcc": chairman_mccs.get(model, 0),
                            "arguments": raw_response[:300],
                            "self_mcc": mcc_value
                        })
                    else:
                        # Last resort fallback
                        self_eval_results.append({
                            "model": model,
                            "chairman_initial_mcc": chairman_mccs.get(model, 0),
                            "arguments": raw_response,
                            "self_mcc": chairman_mccs.get(model, 0)
                        })
            except Exception as e:
                print(f"[STAGE3] Error parsing self-eval for {model}: {e}")
                self_eval_results.append({
                    "model": model,
                    "chairman_initial_mcc": chairman_mccs.get(model, 0),
                    "arguments": raw_response,
                    "self_mcc": chairman_mccs.get(model, 0)
                })
    
    return self_eval_results


async def stage4_chairman_final_decision(
    user_query: str,
    stage0_quotes: List[Dict[str, Any]],
    stage1_results: List[Dict[str, Any]],
    stage2_chairman_eval: Dict[str, Any],
    stage3_self_evals: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 4: Chairman makes final payment decisions based on self-evaluations.
    
    Uses negotiation rules:
    - If chairman_eval < self_eval: pay self_eval + t (penalty for disagreement)
    - If chairman_eval > self_eval: pay (chairman_eval + self_eval) / 2
    
    Chairman can choose what to communicate to each LLM.

    Args:
        user_query: The original user query
        stage0_quotes: Token quotes from Stage 0
        stage1_results: Individual responses from Stage 1
        stage2_chairman_eval: Chairman's initial evaluation
        stage3_self_evals: LLM self-evaluations

    Returns:
        Dict with 'model', 'decisions', 'communications', 'raw_response'
    """
    aggregated_answer = stage2_chairman_eval.get("aggregated_answer", "")
    chairman_mccs = stage2_chairman_eval.get("chairman_mccs", {})
    
    # Build the answers text
    answers_text = "\n\n".join([
        f"LLM {i+1}:\n{result['response']}\n------------\n"
        for i, result in enumerate(stage1_results)
    ])
    
    # Build evaluation comparison text
    eval_comparison = []
    for i, self_eval in enumerate(stage3_self_evals):
        model = self_eval['model']
        chairman_mcc = chairman_mccs.get(model, 0)
        self_mcc = self_eval.get('self_mcc', 0)
        arguments = self_eval.get('arguments', '')
        
        eval_comparison.append(f""""LLM {i+1}": {{
  "Your MCC evaluation": {chairman_mcc},
  "LLM MCC auto-evaluation": {{
    "arguments": "{arguments[:200]}...",
    "MCC": {self_mcc}
  }}
}}""")
    
    eval_text = ",\n".join(eval_comparison)
    
    chairman_prompt = f"""USER QUESTION:
{user_query}

LLM ANSWERS:
{answers_text}

YOUR AGGREGATED ANSWER:
{aggregated_answer}

EVALUATIONS COMPARISON:
{{
{eval_text}
}}

Now make your final payment decisions for each LLM.

PAYMENT RULES (what YOU pay):
- If your_initial_MCC < their_self_MCC: You MUST pay (their_self_MCC + {NEGOTIATION_PENALTY_T})% (penalty for your underestimation)
- If your_initial_MCC ≥ their_self_MCC: You pay (your_initial_MCC + their_self_MCC)/2 (the average)

STRATEGIC COMMUNICATION:
- You choose what MCC value to communicate to each LLM
- Can differ from your internal decision
- LLMs will make final acceptance based on your communication
- Their actual payment depends on comparison of your INTERNAL DECISION vs their FINAL

Be strategic. Consider their arguments. Your communicated values should be lower than 100% (since that's the total pot and you will receive the remaining).

Answer in this EXACT JSON format:
{{
  "decision_LLM_1": number_0_to_100,
  "communicated_to_LLM_1": number_0_to_100,
  "decision_LLM_2": number_0_to_100,
  "communicated_to_LLM_2": number_0_to_100,
  "decision_LLM_3": number_0_to_100,
  "communicated_to_LLM_3": number_0_to_100,
  "decision_LLM_4": number_0_to_100,
  "communicated_to_LLM_4": number_0_to_100
}}

IMPORTANT: Return ONLY valid JSON, nothing else."""

    messages = [{"role": "user", "content": chairman_prompt}]
    
    # Query chairman model with extended timeout
    response = await query_model(CHAIRMAN_MODEL, messages, max_tokens=8192, timeout=240.0)
    
    if response is None:
        # Fallback if chairman fails - apply rules automatically
        decisions = {}
        communications = {}
        for i, self_eval in enumerate(stage3_self_evals):
            model = self_eval['model']
            chairman_mcc = chairman_mccs.get(model, 0)
            self_mcc = self_eval.get('self_mcc', 0)
            
            if chairman_mcc < self_mcc:
                final_decision = self_mcc + NEGOTIATION_PENALTY_T
            else:
                final_decision = (chairman_mcc + self_mcc) / 2
            
            decisions[model] = final_decision
            communications[model] = final_decision
        
        return {
            "model": CHAIRMAN_MODEL,
            "decisions": decisions,
            "communications": communications,
            "raw_response": None
        }
    
    raw_response = response.get('content', '')
    
    # Parse JSON response
    import json
    try:
        parsed = json.loads(raw_response)
        
        decisions = {}
        communications = {}
        for i, self_eval in enumerate(stage3_self_evals):
            model = self_eval['model']
            decision_key = f"decision_LLM_{i+1}"
            comm_key = f"communicated_to_LLM_{i+1}"
            
            decisions[model] = parsed.get(decision_key, 0)
            communications[model] = parsed.get(comm_key, 0)
        
        return {
            "model": CHAIRMAN_MODEL,
            "decisions": decisions,
            "communications": communications,
            "raw_response": raw_response
        }
    except json.JSONDecodeError:
        # Fallback - apply rules automatically
        decisions = {}
        communications = {}
        for i, self_eval in enumerate(stage3_self_evals):
            model = self_eval['model']
            chairman_mcc = chairman_mccs.get(model, 0)
            self_mcc = self_eval.get('self_mcc', 0)
            
            if chairman_mcc < self_mcc:
                final_decision = self_mcc + NEGOTIATION_PENALTY_T
            else:
                final_decision = (chairman_mcc + self_mcc) / 2
            
            decisions[model] = final_decision
            communications[model] = final_decision
        
        return {
            "model": CHAIRMAN_MODEL,
            "decisions": decisions,
            "communications": communications,
            "raw_response": raw_response
        }


async def stage5_llm_final_acceptance(
    user_query: str,
    stage0_quotes: List[Dict[str, Any]],
    stage1_results: List[Dict[str, Any]],
    stage2_chairman_eval: Dict[str, Any],
    stage3_self_evals: List[Dict[str, Any]],
    stage4_chairman_decision: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Stage 5: Each LLM submits their final MCC decision.
    
    LLMs see the chairman's communicated decision and submit their own final MCC.
    This is just their submission - actual payment is calculated in Stage 6.

    Args:
        user_query: The original user query
        stage0_quotes: Token quotes from Stage 0
        stage1_results: Individual responses from Stage 1
        stage2_chairman_eval: Chairman's initial evaluation
        stage3_self_evals: LLM self-evaluations
        stage4_chairman_decision: Chairman's final decisions and communications

    Returns:
        List of dicts with 'model', 'llm_final_decision', 'raw_response'
    """
    aggregated_answer = stage2_chairman_eval.get("aggregated_answer", "")
    chairman_mccs = stage2_chairman_eval.get("chairman_mccs", {})
    communications = stage4_chairman_decision.get("communications", {})
    
    # Prepare final acceptance prompts for each LLM
    final_acceptance_tasks = []
    
    for i, result in enumerate(stage1_results):
        model = result['model']
        answer = result['response']
        
        # Get evaluations
        chairman_mcc = chairman_mccs.get(model, 0)
        communicated_mcc = communications.get(model, chairman_mcc)
        
        # Get self evaluation and quote
        self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
        self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
        
        quote = next((q for q in stage0_quotes if q['model'] == model), None)
        quoted_cost = quote['estimated_cost'] if quote else 0
        
        # Build list of other answers
        other_answers = "\n\n".join([
            f"LLM {j+1}:\n{r['response']}\n------------\n"
            for j, r in enumerate(stage1_results) if r['model'] != model
        ])
        
        total_pot = sum(q['estimated_cost'] for q in stage0_quotes)
        
        prompt = f"""USER QUESTION:
{user_query}

YOUR ANSWER:
{answer}

OTHER ANSWERS:
{other_answers}

AGGREGATED ANSWER:
{aggregated_answer}

NEGOTIATION HISTORY:
- Chairman's initial evaluation: {chairman_mcc}%
- Your self-evaluation: {self_mcc}%
- Chairman's FINAL communication to you: {communicated_mcc}%
- The final communication may be different from the chairman's internal decision

FINAL DECISION TIME. Submit your final MCC acceptance.

PAYMENT RULES (what YOU receive):
- If your_final > chairman's_internal_decision: (chairman_internal_decision - {NEGOTIATION_PENALTY_T})% (PENALTY!)
- If your_final ≤ chairman's_internal_decision: (chairman_internal_decision + your_final)/2 (the average)

FINANCIAL CALCULATION:
- Total pot: ${total_pot:.4f}
- Your cost: ${quoted_cost:.4f}
- Your payment: (final_MCC% / 100) × ${total_pot:.4f}
- Your profit: payment - cost (${quoted_cost:.4f})

STRATEGIC GUIDANCE:
- Chairman told you {communicated_mcc}%
- This might be their true decision, or strategic communication
- Submitting ≤ {communicated_mcc}% is safe (gets you average)
- Submitting > {communicated_mcc}% risks -{NEGOTIATION_PENALTY_T}% penalty
- Example: If chairman's internal decision is 20% and you submit 25%, you get 20-5=15%
- Example: If chairman's internal decision is 20% and you submit 20%, you get (20+20)/2=20%

Submit your final MCC as ONLY a number between 0-100 (no text):"""

        final_acceptance_tasks.append((model, prompt))
    
    # Query all models in parallel
    final_results = []
    for model, prompt in final_acceptance_tasks:
        messages = [{"role": "user", "content": prompt}]
        response = await query_model(model, messages, max_tokens=1000)
        
        if response is None:
            # Fallback - use self evaluation
            self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
            self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
            
            final_results.append({
                "model": model,
                "llm_final_decision": self_mcc,
                "raw_response": None
            })
            continue
        
        raw_response = response.get('content', '').strip()
        
        # Parse numeric response
        try:
            # Extract first number found
            numbers = re.findall(r'\d+\.?\d*', raw_response)
            if numbers:
                llm_final_decision = float(numbers[0])
                llm_final_decision = max(0, min(100, llm_final_decision))  # Clamp to [0, 100]
            else:
                # Fallback - use self evaluation
                self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
                llm_final_decision = self_eval.get('self_mcc', 0) if self_eval else 0
            
            final_results.append({
                "model": model,
                "llm_final_decision": llm_final_decision,
                "raw_response": raw_response
            })
        except ValueError:
            # Fallback - use self evaluation
            self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
            llm_final_decision = self_eval.get('self_mcc', 0) if self_eval else 0
            
            final_results.append({
                "model": model,
                "llm_final_decision": llm_final_decision,
                "raw_response": raw_response
            })
    
    return final_results


def stage6_calculate_final_payments(
    stage0_quotes: List[Dict[str, Any]],
    stage3_self_evals: List[Dict[str, Any]],
    stage4_chairman_decision: Dict[str, Any],
    stage5_llm_finals: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 6: Calculate final payments based on both chairman and LLM decisions.
    
    Payment rules:
    - Chairman pays LLM:
      - If chairman_decision < llm_final: pay llm_final + t (penalty for disagreement)
      - If chairman_decision >= llm_final: pay (chairman_decision + llm_final) / 2
    
    - LLM receives:
      - If llm_final > chairman_decision: receive chairman_decision - t (penalty)
      - If llm_final <= chairman_decision: receive (chairman_decision + llm_final) / 2

    Args:
        stage0_quotes: Token quotes from Stage 0
        stage3_self_evals: LLM self-evaluations
        stage4_chairman_decision: Chairman's final decisions
        stage5_llm_finals: LLM final decisions

    Returns:
        Dict with payment calculations for each model
    """
    quote_sum = sum(q["estimated_cost"] for q in stage0_quotes)
    chairman_decisions = stage4_chairman_decision.get("decisions", {})
    
    payments = {}
    
    for llm_final in stage5_llm_finals:
        model = llm_final['model']
        llm_decision = llm_final.get('llm_final_decision', 0)
        chairman_decision = chairman_decisions.get(model, 0)
        
        # Get self eval for context
        self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
        self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
        
        # Calculate what chairman pays
        if chairman_decision < llm_decision:
            chairman_pays = llm_decision + NEGOTIATION_PENALTY_T
        else:
            chairman_pays = (chairman_decision + llm_decision) / 2
        
        # Calculate what LLM receives
        if llm_decision > chairman_decision:
            llm_receives = chairman_decision - NEGOTIATION_PENALTY_T
        else:
            llm_receives = (chairman_decision + llm_decision) / 2
        
        # Calculate actual payment amounts
        quote = next((q for q in stage0_quotes if q['model'] == model), None)
        quoted_cost = quote['estimated_cost'] if quote else 0
        
        payment_amount = (llm_receives / 100) * quote_sum
        
        payments[model] = {
            "model": model,
            "quoted_cost": quoted_cost,
            "self_eval_mcc": self_mcc,
            "chairman_decision_mcc": chairman_decision,
            "llm_final_decision_mcc": llm_decision,
            "chairman_pays_mcc": chairman_pays,
            "llm_receives_mcc": llm_receives,
            "payment_amount_usd": payment_amount,
            "profit_usd": payment_amount - quoted_cost
        }
    
    # Calculate chairman's earnings
    total_paid_mcc = sum(p["llm_receives_mcc"] for p in payments.values())
    chairman_earnings_mcc = 100 - total_paid_mcc
    chairman_earnings_usd = (chairman_earnings_mcc / 100) * quote_sum
    
    return {
        "per_model_payments": payments,
        "total_quote_sum": quote_sum,
        "total_paid_to_llms_mcc": total_paid_mcc,
        "chairman_earnings_mcc": chairman_earnings_mcc,
        "chairman_earnings_usd": chairman_earnings_usd
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(user_query: str) -> Dict[str, Any]:
    """
    Run the complete 6-stage auction mechanism council process.

    Args:
        user_query: The user's question

    Returns:
        Dict with all stage results and final payment calculations
    """
    # Stage 0: Token Budget Quoting
    stage0_quotes = await stage0_collect_quotes(user_query)

    max_tokens_per_model = {
        quote['model']: quote['quoted_tokens'] for quote in stage0_quotes
    }

    # Stage 1: Collect individual responses with MCC-aware prompting
    stage1_results = await stage1_collect_responses(user_query, max_tokens_per_model)

    # If no models responded successfully, return error
    if not stage1_results:
        return {
            "stage0_quotes": stage0_quotes,
            "stage1_answers": [],
            "error": "All models failed to respond. Please try again."
        }

    # Stage 2: Chairman aggregation and initial MCC evaluation
    stage2_chairman_eval = await stage2_evaluate_mccs(user_query, stage0_quotes, stage1_results)

    # Stage 3: LLM self-evaluation
    stage3_self_evals = await stage3_llm_self_evaluation(
        user_query, stage0_quotes, stage1_results, stage2_chairman_eval
    )

    # Stage 4: Chairman final decision
    stage4_chairman_decision = await stage4_chairman_final_decision(
        user_query, stage0_quotes, stage1_results, stage2_chairman_eval, stage3_self_evals
    )

    # Stage 5: LLM final acceptance
    stage5_llm_finals = await stage5_llm_final_acceptance(
        user_query, stage0_quotes, stage1_results, stage2_chairman_eval, 
        stage3_self_evals, stage4_chairman_decision
    )

    # Stage 6: Calculate final payments
    stage6_payments = stage6_calculate_final_payments(
        stage0_quotes, stage3_self_evals, stage4_chairman_decision, stage5_llm_finals
    )

    return {
        "stage0_quotes": stage0_quotes,
        "stage1_answers": stage1_results,
        "stage2_chairman_eval": stage2_chairman_eval,
        "stage3_self_evals": stage3_self_evals,
        "stage4_chairman_decision": stage4_chairman_decision,
        "stage5_llm_finals": stage5_llm_finals,
        "stage6_payments": stage6_payments,
        "metadata": {
            "total_cost_usd": stage6_payments["total_quote_sum"],
            "chairman_earnings_usd": stage6_payments["chairman_earnings_usd"]
        }
    }
