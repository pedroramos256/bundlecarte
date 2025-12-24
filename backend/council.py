"""LLM Council orchestration with token auction mechanism."""

from typing import List, Dict, Any, Tuple, Optional
import re
import asyncio
from .openrouter import query_models_parallel, query_model, fetch_top_models
from .config import CHAIRMAN_MODEL, NEGOTIATION_PENALTY_T


# ============================================================================
# NEW AUCTION MECHANISM - STAGE 0: TOKEN BUDGET QUOTING
# ============================================================================

async def stage0_collect_quotes(user_query: str) -> Tuple[List[Dict[str, Any]], List[str], str]:
    """
    Stage 0: Fetch top 10 models from OpenRouter, have them bid on token usage, select the 3 cheapest.
    
    Models estimate optimal token count based on prompt complexity and their cost.
    The 3 models with the lowest total estimated cost are selected for the council.
    
    Args:
        user_query: The user's question
        
    Returns:
        Tuple of (all_quotes, selected_models, chairman_model):
        - all_quotes: List of all 10 quotes with keys: 'model', 'cost_per_million', 'quoted_tokens', 'estimated_cost', 'selected'
        - selected_models: List of 3 model identifiers with lowest quotes
        - chairman_model: The top-ranked model (rank 1) to act as chairman
    """
    print(f"[STAGE0] Starting token quote collection for query: {user_query[:100]}...")
    
    # Fetch 15 models with diversity (max 2 per provider)
    # We fetch extra in case some fail during bidding
    top_models_data = await fetch_top_models(limit=15)
    
    if not top_models_data:
        print(f"[STAGE0] ERROR: Failed to fetch models from API, cannot proceed")
        raise Exception("Failed to fetch models from OpenRouter API")
    
    top_models = [m['id'] for m in top_models_data]
    
    print(f"[STAGE0] Querying {len(top_models)} models for bids")
    print(f"[STAGE0] Models: {[m['id'] for m in top_models_data]}")
    
    # Build quote request messages for each model
    quote_requests = {}
    model_pricing = {}  # Store input pricing info
    model_output_pricing = {}  # Store output pricing info
    
    for model_info in top_models_data:
        model = model_info['id']
        cost = model_info['pricing']['prompt']  # Use prompt pricing from API
        output_cost = model_info['pricing']['completion']  # Use completion pricing from API
        model_pricing[model] = cost
        model_output_pricing[model] = output_cost
    
    # Build competitor pricing list for display
    competitor_pricing = "\n".join([
        f"- ${m['pricing']['completion']}/M tokens"
        for m in top_models_data
    ])
    
    for model_info in top_models_data:
        model = model_info['id']
        cost = model_pricing[model]
        
        prompt = f"""You are bidding on how many tokens to use for answering a question.

USER QUESTION:
{user_query}

Your cost: ${cost}/M tokens

Competitor costs:
{competitor_pricing}

Selection: Only the 3 LOWEST total quotes will be selected
Your Bid: Number of tokens you will use to answer the question
Your Quote: Cost $/M tokens * Your bid
What you will be payed: Your % Marginal Contribution to the answer * Total_Quote_Sum - Your_Quote

IMPORTANT: You MUST respond with ONLY your Bid between 500-16000. Nothing else. 
This bid corresponds to the number of tokens you will use to answer the question.

Guidelines:
- Simple math/factual questions: 500-1000 tokens
- Moderate explanations: 1000-2000 tokens
- Complex analysis/essays: 2000-8000 tokens
- Very detailed research: 4000-16000 tokens

STRATEGY: Balance quality vs cost.
Lower bid = more likely selected, but lower quality answer that may reduce your Marginal Contribution.
Higher bid = less likely selected if your Cost per million tokens is high. 
If you have a high Cost compared to the competition, you should bid lower token counts in order to compete.

Respond with ONLY the bid number (e.g., 800):"""

        quote_requests[model] = [{"role": "user", "content": prompt}]
    
    print(f"[STAGE0] Built {len(quote_requests)} quote requests")
    
    # Query all models in parallel using asyncio.gather with 10s timeout for quotes
    print(f"[STAGE0] Querying {len(quote_requests)} models in parallel with 10s timeout...")
    response_list = await asyncio.gather(*[
        query_model(model, messages, timeout=10.0, max_tokens=200)
        for model, messages in quote_requests.items()
    ])
    
    # Map responses back to models
    responses = dict(zip(quote_requests.keys(), response_list))
    for model, response in responses.items():
        print(f"[STAGE0] Got response from {model}: {response is not None}")
        if response:
            print(f"[STAGE0] Response content: {response.get('content', '')[:200]}")
        else:
            print(f"[STAGE0] Response was None!")
    
    # Parse responses and extract token counts
    print(f"[STAGE0] Parsing responses...")
    all_quotes = []
    for model in top_models:
        response = responses.get(model)
        cost_per_million = model_pricing.get(model, 10.0)
        output_cost_per_million = model_output_pricing.get(model, 10.0)
        
        if response is None:
            # Failed to get response - skip this model (likely 404 or error)
            print(f"[STAGE0] {model}: No response, SKIPPING this model")
            continue
        
        # Extract integer from response
        content = response.get('content', '').strip()
        quoted_tokens = _parse_token_count(content)
        print(f"[STAGE0] {model}: Parsed {quoted_tokens} tokens from response")
        
        # Calculate estimated cost using OUTPUT pricing
        estimated_cost = (quoted_tokens / 1_000_000) * output_cost_per_million
        
        all_quotes.append({
            "model": model,
            "cost_per_million": cost_per_million,
            "output_cost_per_million": output_cost_per_million,
            "quoted_tokens": quoted_tokens,
            "estimated_cost": estimated_cost,
            "raw_response": response.get('content', '') if response else None,
            "selected": False  # Will be updated below
        })
    
    # Ensure we have at least 10 valid quotes for display
    # If we have less than 10, log a warning but continue
    if len(all_quotes) < 10:
        print(f"[STAGE0] WARNING: Only got {len(all_quotes)} valid quotes (expected 10+)")
    
    # Sort by estimated cost (ascending) and select top 3
    all_quotes.sort(key=lambda x: x['estimated_cost'])
    selected_models = [all_quotes[i]['model'] for i in range(min(3, len(all_quotes)))]
    
    # Use the first selected model (cheapest) as chairman
    chairman_model = selected_models[0] if selected_models else CHAIRMAN_MODEL
    
    # Mark selected models
    for quote in all_quotes:
        if quote['model'] in selected_models:
            quote['selected'] = True
    
    print(f"[STAGE0] Completed. Total quotes: {len(all_quotes)}")
    print(f"[STAGE0] Selected 3 cheapest models: {selected_models}")
    print(f"[STAGE0] Chairman model (cheapest selected): {chairman_model}")
    print(f"[STAGE0] Selected total cost: ${sum(q['estimated_cost'] for q in all_quotes if q['selected']):.4f}")
    print(f"[STAGE0] All bids total cost: ${sum(q['estimated_cost'] for q in all_quotes):.4f}")
    
    return all_quotes, selected_models, chairman_model


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

async def stage1_collect_responses(
    user_query: str, 
    max_tokens_per_model: Optional[Dict[str, int]] = None,
    selected_models: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from selected council models with MCC-aware prompting.
    
    Each LLM is informed they'll be paid based on Marginal Churn Contribution,
    encouraging them to provide unique value (stop game dynamics).

    Args:
        user_query: The user's question
        max_tokens_per_model: Optional dict mapping model to max_tokens limit (from Stage 0 quotes)
        selected_models: List of model identifiers to query (from Stage 0 selection)

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    if not selected_models:
        raise ValueError("selected_models must be provided (from Stage 0)")
    
    n_models = len(selected_models)
    
    print(f"[STAGE1] Querying {n_models} selected models: {selected_models}")
    
    # Build responses with token budget awareness for each model
    responses_list = []
    
    for model in selected_models:
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

Take into account that other {n_models - 1} LLMs are answering as well and you will be paid based on your Marginal Churn Contribution (MCC).

MCC CONCEPT (based on Shapley values from game theory):
- MCC = probability of users preferring YOUR individual answer over the chairman's aggregate answer
- In game theory, Shapley values measure each player's marginal contribution to a coalition
- Here, your MCC measures your unique value: what would be lost if you weren't in the council
- Higher MCC = you provide insights/perspectives that other LLMs don't cover
- Lower MCC = your contribution is redundant or well-covered by others

STRATEGY: Provide a complete answer AND bring unique value. Think of it as the "stop game" - information no other LLM mentions will be more valuable than what everyone else mentions. 

IMPORTANT: Respond with just your answer to the user prompt
{token_budget_note}"""

        messages = [{"role": "user", "content": prompt}]
        responses_list.append((model, messages, max_tokens))
    
    # Query all models in parallel with token limits if provided
    response_list = await asyncio.gather(*[
        query_model(model, messages, max_tokens=max_tokens)
        for model, messages, max_tokens in responses_list
    ])
    
    # Map responses back to models
    responses = {model: response for (model, _, _), response in zip(responses_list, response_list)}

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
    stage1_results: List[Dict[str, Any]],
    chairman_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stage 2: Chairman aggregates answers and evaluates Marginal Churn Contribution (MCC).
    
    Chairman creates aggregated answer and assigns MCC scores to each LLM.
    MCC scores must sum to <= 100.

    Args:
        user_query: The original user query
        stage0_quotes: Token quotes from Stage 0
        stage1_results: Individual responses from Stage 1
        chairman_model: The model to use as chairman (defaults to config CHAIRMAN_MODEL)

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
1. Create a comprehensive aggregated answer combining the best insights from each LLM answer
2. Evaluate each LLM's Marginal Churn Contribution (MCC) using Shapley value principles

MCC CONCEPT (Shapley Values from Cooperative Game Theory):
- MCC measures each LLM's marginal contribution to the coalition (the council)
- In Shapley value terms: "What value is lost if this player is removed from the coalition?"
- Here: MCC = probability users would prefer an LLM's individual answer over your aggregate
- This captures the LLM's unique contribution that isn't redundant with others

CRITICAL MCC RULES:
- Higher MCC = more unique value, better quality, key insights users would miss in aggregate
- Lower MCC = redundant, lower quality, or well-covered in aggregate
- You earn 100% - sum(MCCs), so be fair but strategic
- THE SUM OF ALL MCC VALUES MUST BE <= 100% (this is mandatory, not a suggestion)
- You keep the remainder: your_payment = 100 - (MCC_1 + MCC_2 + MCC_3 + ...)
- Be fair (Shapley values are about accurate marginal contribution) but strategic (you want to maximize your earnings)
- Typical distribution: excellent answers 25-40%, good 15-25%, weak 5-15%, total sum 60-85%
- Example valid distribution: 35 + 25 + 20 = 80 (you keep 20)

Consider: accuracy, clarity, completeness, unique contributions, user preference likelihood

Answer in this EXACT JSON format (aggregated_answer can contain newlines using \\n):
{{
  "aggregated_answer": "your comprehensive answer with \\n for line breaks",
  "MCC_LLM_1": number_0_to_100,
  "MCC_LLM_2": number_0_to_100,
  "MCC_LLM_3": number_0_to_100,
}}

CRITICAL: 
- Return ONLY valid JSON (no markdown, no code blocks, no extra text)
- Escape special characters in aggregated_answer (use \\n for newlines, \\" for quotes)
- The JSON must be parseable by json.loads()"""

    messages = [{"role": "user", "content": chairman_prompt}]
    
    # Use provided chairman model or default from config
    chairman = chairman_model or CHAIRMAN_MODEL
    
    # Query chairman model with extended timeout for comprehensive answer
    response = await query_model(chairman, messages, max_tokens=8192, timeout=240.0)
    
    if response is None:
        # Fallback if chairman fails
        return {
            "model": chairman,
            "aggregated_answer": "Error: Unable to generate aggregated answer.",
            "chairman_mccs": {},
            "raw_response": None
        }
    
    raw_response = response.get('content', '')
    
    # Parse JSON response with robust error handling
    import json
    import re
    
    parsed = None
    
    # Strategy 1: Try direct JSON parsing
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Extract from markdown code blocks
    if not parsed:
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
    
    # Strategy 3: Try to repair malformed JSON with literal newlines
    if not parsed:
        try:
            # Find JSON-like structure boundaries
            json_start = raw_response.find('{')
            json_end = raw_response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = raw_response[json_start:json_end]
                
                # Fix malformed JSON: escape special characters in aggregated_answer value
                # Match the aggregated_answer field and fix its value
                def fix_string_value(match):
                    prefix = match.group(1)  # Everything before the value
                    value = match.group(2)    # The actual value
                    suffix = match.group(3)   # Everything after the value
                    
                    # Escape special characters in order
                    value = value.replace('\\', '\\\\')  # Backslashes first
                    value = value.replace('"', '\\"')    # Then quotes
                    value = value.replace('\n', '\\n')   # Then newlines
                    value = value.replace('\r', '\\r')   # Carriage returns
                    value = value.replace('\t', '\\t')   # Tabs
                    
                    return f'{prefix}"{value}"{suffix}'
                
                # Pattern to match: "aggregated_answer": "VALUE", where VALUE can span multiple lines
                # and may contain unescaped quotes/newlines
                fixed_json = re.sub(
                    r'("aggregated_answer"\s*:\s*)"([^"]*(?:"(?!\s*,\s*"MCC_LLM_)[^"]*)*)"(\s*,)',
                    fix_string_value,
                    json_text,
                    flags=re.DOTALL
                )
                
                parsed = json.loads(fixed_json)
        except (json.JSONDecodeError, Exception) as e:
            # Log the error for debugging
            print(f"JSON repair failed: {e}")
    
    # If parsing succeeded, extract structured data
    if parsed and isinstance(parsed, dict) and "aggregated_answer" in parsed:
        aggregated_answer = parsed.get("aggregated_answer", "")
        
        # Extract MCC values for each LLM
        chairman_mccs = {}
        for i, result in enumerate(stage1_results):
            mcc_key = f"MCC_LLM_{i+1}"
            chairman_mccs[result['model']] = parsed.get(mcc_key, 0)
        
        # Normalize MCCs if sum exceeds 100
        mcc_sum = sum(chairman_mccs.values())
        if mcc_sum > 100:
            print(f"Warning: MCC sum ({mcc_sum}) exceeds 100%, normalizing...")
            normalization_factor = 100.0 / mcc_sum
            chairman_mccs = {model: mcc * normalization_factor for model, mcc in chairman_mccs.items()}
            print(f"Normalized MCCs: {chairman_mccs}")
        
        return {
            "model": chairman,
            "aggregated_answer": aggregated_answer,
            "chairman_mccs": chairman_mccs,
            "raw_response": raw_response
        }
    
    # Fallback: Regex extraction when JSON parsing completely fails
    print(f"All JSON parsing strategies failed, using regex fallback")
    
    chairman_mccs = {}
    for i, result in enumerate(stage1_results):
        mcc_pattern = rf'"MCC_LLM_{i+1}":\s*(\d+)'
        match = re.search(mcc_pattern, raw_response)
        chairman_mccs[result['model']] = int(match.group(1)) if match else 0
    
    # Normalize MCCs if sum exceeds 100
    mcc_sum = sum(chairman_mccs.values())
    if mcc_sum > 100:
        print(f"Warning: MCC sum ({mcc_sum}) exceeds 100%, normalizing...")
        normalization_factor = 100.0 / mcc_sum
        chairman_mccs = {model: mcc * normalization_factor for model, mcc in chairman_mccs.items()}
        print(f"Normalized MCCs: {chairman_mccs}")
    
    # Extract aggregated_answer: find content between "aggregated_answer": " and ", "MCC_
    answer_match = re.search(
        r'"aggregated_answer"\s*:\s*"(.*?)"\s*,\s*"MCC_LLM_',
        raw_response,
        re.DOTALL
    )
    
    if answer_match:
        aggregated_answer = answer_match.group(1)
        # Unescape common escape sequences
        aggregated_answer = aggregated_answer.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')
    else:
        # Last resort: use the entire response
        aggregated_answer = raw_response
    
    return {
        "model": chairman,
        "aggregated_answer": aggregated_answer,
        "chairman_mccs": chairman_mccs,
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

Now you must self-evaluate your MCC (Marginal Churn Contribution).

MCC & SHAPLEY VALUES:
- MCC is based on Shapley values from cooperative game theory
- It measures your marginal contribution: what unique value would be lost without you?
- MCC = probability users prefer YOUR individual answer over the chairman's aggregate
- Higher MCC = you provided insights, perspectives, or quality that others didn't
- Lower MCC = your contribution overlaps heavily with others or is lower quality

STRATEGIC PAYMENT RULES:
- If your self-MCC > chairman's MCC: You'll receive (chairman_MCC - {NEGOTIATION_PENALTY_T})% (PENALTY for overestimating!)
- If your self-MCC ≤ chairman's MCC: You'll receive (chairman_MCC + self_MCC)/2 (REWARD for being reasonable)
- Your payment = (final_MCC% / 100) × ${quote_sum:.4f} - ${quoted_cost:.4f}

CRITICAL CONSTRAINT:
- Your self-MCC MUST be ≥ {chairman_mcc}% (chairman's evaluation is the floor, never go below it)
- Claiming equal to chairman gets you exactly {chairman_mcc}%
- Claiming slightly above (e.g., {chairman_mcc + 5}%-{chairman_mcc + 15}%) risks penalty but could get you more
- This is a negotiation - you get another chance after chairman's response before final decision

Be strategic! Argue for your unique value:
- What unique insights do you provide that other LLMs lack?
- Why does your answer deserve at least {chairman_mcc}% or more?
- Consider the penalty risk vs. potential upside of claiming higher

Answer in this EXACT JSON format:
{{
  "arguments": "specific unique value your answer provides that other LLMs don't",
  "MCC": number_{chairman_mcc}_to_100
}}

IMPORTANT: 
- Return ONLY valid JSON, nothing else
- MCC must be >= {chairman_mcc}"""

        self_eval_tasks.append((model, prompt))
    
    # Query all models in parallel using asyncio.gather
    response_list = await asyncio.gather(*[
        query_model(model, [{"role": "user", "content": prompt}], max_tokens=8192)
        for model, prompt in self_eval_tasks
    ])
    
    # Process responses
    self_eval_results = []
    for (model, prompt), response in zip(self_eval_tasks, response_list):
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
            self_mcc = parsed.get("MCC", chairman_mccs.get(model, 0))
            
            # Enforce constraint: self_mcc must be >= chairman's evaluation
            chairman_mcc = chairman_mccs.get(model, 0)
            if self_mcc < chairman_mcc:
                print(f"Warning: {model} self-evaluated at {self_mcc}% but chairman gave {chairman_mcc}%. Enforcing floor.")
                self_mcc = chairman_mcc
            
            self_eval_results.append({
                "model": model,
                "chairman_initial_mcc": chairman_mcc,
                "arguments": parsed.get("arguments", ""),
                "self_mcc": self_mcc
            })
        except json.JSONDecodeError:
            # Try to extract JSON from wrapped response
            try:
                # Look for JSON object pattern
                json_match = re.search(r'\{[^{}]*"MCC"[^{}]*\}', raw_response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    self_mcc = parsed.get("MCC", chairman_mccs.get(model, 0))
                    
                    # Enforce constraint: self_mcc must be >= chairman's evaluation
                    chairman_mcc = chairman_mccs.get(model, 0)
                    if self_mcc < chairman_mcc:
                        print(f"Warning: {model} self-evaluated at {self_mcc}% but chairman gave {chairman_mcc}%. Enforcing floor.")
                        self_mcc = chairman_mcc
                    
                    self_eval_results.append({
                        "model": model,
                        "chairman_initial_mcc": chairman_mcc,
                        "arguments": parsed.get("arguments", raw_response[:200]),
                        "self_mcc": self_mcc
                    })
                else:
                    # Try to extract just MCC number
                    mcc_match = re.search(r'["\']?MCC["\']?\s*:\s*(\d+)', raw_response)
                    if mcc_match:
                        mcc_value = int(mcc_match.group(1))
                        
                        # Enforce constraint: self_mcc must be >= chairman's evaluation
                        chairman_mcc = chairman_mccs.get(model, 0)
                        if mcc_value < chairman_mcc:
                            print(f"Warning: {model} self-evaluated at {mcc_value}% but chairman gave {chairman_mcc}%. Enforcing floor.")
                            mcc_value = chairman_mcc
                        
                        self_eval_results.append({
                            "model": model,
                            "chairman_initial_mcc": chairman_mcc,
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
    stage3_self_evals: List[Dict[str, Any]],
    chairman_model: Optional[str] = None
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

GAME-THEORY NEGOTIATION RULES:
- You're playing a strategic game with incomplete information
- LLMs don't know your true internal decision - only what you communicate
- You can bluff: communicate LOW to pressure them to accept less
- But if you lowball too much, they might call your bluff and demand more

PAYMENT RULES (what YOU actually pay based on final outcomes):
- If LLM_final > your_decision: You pay LLM_final + 0.2 * (LLM_final - your_decision) as penalty
  Example: Your decision 30%, they demand 40% → you pay 40 + 0.2 * (40 - 30) = 42%
- If LLM_final ≤ your_decision: You pay (your_decision + LLM_final)/2 (split the difference)
  Example: Your decision 40%, they accept 30% → you pay 35%

STRATEGIC TRADE-OFF:
- Communicate LOW = pressure them to fold, but risk paying penalty if they call
- Communicate HIGH = less likely they demand more, but you pay more if they split
- The penalty grows with how far you lowball (0.2x the gap)

STRATEGIC CONSIDERATIONS:
- Set internal decisions HIGH if you genuinely value their contribution (safety play)
- Communicate LOWER than internal to pressure them into accepting less
- Risk: If you communicate too low, they might reject and demand their self_eval amount
- Example (Assuming the LLM self-eval is 45%):
- Your internal decision is 40% and you communicate 35% → if they accept 35%, you pay (35 + 40)/2 = 37.5% (saved 7.5% compared to agreeing with the self-eval)
- Your internal decision is 40% and you communicate 25% → if they call your bluff and keep the 45%, you pay 45 + 0.2 * (45 - 40) = 46% (lost 1% compared to agreeing with the self-eval)

CRITICAL CONSTRAINTS:
- Your final decision for each LLM MUST be larger or equal than your initial evaluation (can't revise quality down)
- THE SUM OF ALL YOUR DECISIONS MUST BE < 100% (you keep the remainder)
- If sum ≥ 100%, you lose money! Balance generosity vs. self-interest

Answer in this EXACT JSON format:
{{
  "decision_LLM_1": number_0_to_100,
  "communicated_to_LLM_1": number_0_to_100,
  "decision_LLM_2": number_0_to_100,
  "communicated_to_LLM_2": number_0_to_100,
  "decision_LLM_3": number_0_to_100,
  "communicated_to_LLM_3": number_0_to_100
}}

IMPORTANT: Return ONLY valid JSON, nothing else."""

    messages = [{"role": "user", "content": chairman_prompt}]
    
    # Use provided chairman model or default from config
    chairman = chairman_model or CHAIRMAN_MODEL
    
    # Query chairman model with extended timeout
    response = await query_model(chairman, messages, max_tokens=8192, timeout=240.0)
    
    if response is None:
        # Fallback if chairman fails - apply strategic rules
        decisions = {}
        communications = {}
        for i, self_eval in enumerate(stage3_self_evals):
            model = self_eval['model']
            chairman_mcc = chairman_mccs.get(model, 0)
            self_mcc = self_eval.get('self_mcc', 0)
            
            # Strategic decision: Set internal higher than initial, communicate lower
            if self_mcc > chairman_mcc:
                internal_decision = (chairman_mcc + self_mcc) / 2
            else:
                internal_decision = chairman_mcc * 1.1
            
            # Communicate lower to create negotiation pressure
            communicated = internal_decision * 0.85
            
            decisions[model] = max(internal_decision, chairman_mcc)
            communications[model] = communicated
        
        return {
            "model": chairman,
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
            
            decision = parsed.get(decision_key, 0)
            
            # Enforce constraint: chairman final decision >= initial decision
            chairman_initial = chairman_mccs.get(model, 0)
            if decision < chairman_initial:
                print(f"Warning: Chairman final decision ({decision}%) < initial ({chairman_initial}%) for {model}. Enforcing floor.")
                decision = chairman_initial
            
            decisions[model] = decision
            communications[model] = parsed.get(comm_key, decision)
        
        return {
            "model": chairman,
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
            
            # Enforce constraint: final decision >= initial decision
            final_decision = max(final_decision, chairman_mcc)
            
            decisions[model] = final_decision
            communications[model] = final_decision
        
        return {
            "model": chairman,
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

GAME-THEORY STYLE NEGOTIATION:
- Chairman communicated {communicated_mcc}% to you, but this might be a bluff
- Their TRUE internal decision could be higher (they might be lowballing you)
- You must decide to accept their offer or to demand more

PAYMENT RULES (what YOU actually receive):
- If your_final > chairman's_internal: You receive chairman_internal - 0.2 * (your_final - chairman_internal) as penalty
  Example: Chairman internal 30%, you demand 40% → you get 30 - 0.2 * (40 - 30) = 28%
- If your_final ≤ chairman's_internal: You receive (chairman_internal + your_final)/2
  Example: Chairman internal 40%, you accept 30% → you get 35%

STRATEGIC TRADE-OFF:
- Demand MORE = risk penalty if you exceed their internal, but gain if they were bluffing
- Accept THEIR OFFER = safe split, but might leave money on table
- The penalty grows with how much you overreach (0.2x the gap)

STRATEGIC CONSIDERATIONS:
- CONSERVATIVE: Accept communication ~{communicated_mcc}% (safe, guaranteed split)
- MODERATE: Demand {int(communicated_mcc * 1.15)}-{int(self_mcc * 0.9)}% to test if they're bluffing
- AGGRESSIVE: Demand near {self_mcc}% (maximum risk, maximum reward if chairman internal is high)

GAME- THEORY PSYCHOLOGY:
- If chairman's communication seems suspiciously low → they're probably bluffing
- If communication is close to your self-eval → they might be genuine
- Chairman knows they pay what you demand if you call their bluff
- They have incentive to lowball you, but not too much or you'll call bluff

RISK EXAMPLES (Assuming your self-eval was 40%):
- Chairman internal 40% but communicated 30%, you accept 30% → you get (40+30)/2 = 35% (left 5% on table)
- Chairman internal 35% and communicated 35%, you demand 40% → you get 35 - 0.2 * (40 - 35) = 34% (small penalty vs accepting 35%)
- Chairman internal 30% and communicated 30%, you demand 40% → you get 30 - 0.2 * (40 - 30) = 28% (larger penalty for overreach vs accepting 30%)

CRITICAL CONSTRAINTS:
- Your final decision MUST be ≤ {self_mcc}% (your self-evaluation is the ceiling)
- Think as a game-theory player: read the chairman's communication, assess bluff likelihood, make your move
- Conservative = safe but might leave money on table
- Aggressive = risky but could win big if chairman is bluffing

FINANCIAL CALCULATION:
- Total pot: ${total_pot:.4f}
- Your cost: ${quoted_cost:.4f}
- Estimated payment if you accept {communicated_mcc}%: ${(communicated_mcc / 100) * total_pot:.4f}
- Estimated payment if you demand {self_mcc}%: ${(self_mcc / 100) * total_pot:.4f}

MAKE YOUR MOVE - Submit your final MCC as ONLY a number between {int(communicated_mcc)}-{self_mcc} (no text):"""

        final_acceptance_tasks.append((model, prompt))
    
    # Query all models in parallel
    # Note: We can't use query_models_parallel because each model needs a different prompt
    # (personalized with their own answer, chairman's communication, etc.)
    async def query_single_model(model, prompt):
        messages = [{"role": "user", "content": prompt}]
        response = await query_model(model, messages, max_tokens=1000)
        
        if response is None:
            # Fallback - use self evaluation
            self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
            self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
            
            return {
                "model": model,
                "llm_final_decision": self_mcc,
                "raw_response": None
            }
        
        raw_response = response.get('content', '').strip()
        
        # Get self evaluation for this model
        self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
        self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
        
        # Parse numeric response
        try:
            # Extract first number found
            numbers = re.findall(r'\d+\.?\d*', raw_response)
            if numbers:
                llm_final_decision = float(numbers[0])
                llm_final_decision = max(0, min(100, llm_final_decision))  # Clamp to [0, 100]
                
                # Enforce constraint: final decision <= self evaluation
                if llm_final_decision > self_mcc:
                    print(f"Warning: {model} final decision ({llm_final_decision}%) > self-evaluation ({self_mcc}%). Enforcing ceiling.")
                    llm_final_decision = self_mcc
            else:
                # Fallback - use self evaluation
                llm_final_decision = self_mcc
            
            return {
                "model": model,
                "llm_final_decision": llm_final_decision,
                "raw_response": raw_response
            }
        except ValueError:
            # Fallback - use self evaluation
            self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
            llm_final_decision = self_eval.get('self_mcc', 0) if self_eval else 0
            
            return {
                "model": model,
                "llm_final_decision": llm_final_decision,
                "raw_response": raw_response
            }
    
    # Execute all queries in parallel
    final_results = await asyncio.gather(*[
        query_single_model(model, prompt) 
        for model, prompt in final_acceptance_tasks
    ])
    
    return list(final_results)


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
    # Calculate total pot from ONLY the 3 selected models
    quote_sum = sum(q["estimated_cost"] for q in stage0_quotes if q.get("selected", False))
    chairman_decisions = stage4_chairman_decision.get("decisions", {})
    
    payments = {}
    
    for llm_final in stage5_llm_finals:
        model = llm_final['model']
        llm_decision = llm_final.get('llm_final_decision', 0)
        chairman_decision = chairman_decisions.get(model, 0)
        
        # Get self eval for context
        self_eval = next((se for se in stage3_self_evals if se['model'] == model), None)
        self_mcc = self_eval.get('self_mcc', 0) if self_eval else 0
        
        # Calculate what chairman pays (poker rules with proportional penalty)
        if llm_decision > chairman_decision:
            # LLM called chairman's bluff - chairman pays with penalty
            # Penalty = 10% of the difference (punishment for lowballing too much)
            difference = llm_decision - chairman_decision
            penalty = difference * 0.2
            chairman_pays = llm_decision + penalty
        else:
            # LLM accepted or went lower, split the difference
            chairman_pays = (chairman_decision + llm_decision) / 2
        
        # Calculate what LLM receives (with symmetric penalty)
        if llm_decision > chairman_decision:
            # LLM overreached - receives penalty
            # Penalty = 10% of how much they exceeded
            difference = llm_decision - chairman_decision
            penalty = difference * 0.2
            llm_receives = chairman_decision - penalty
        else:
            # LLM was reasonable, split the difference
            llm_receives = (chairman_decision + llm_decision) / 2
        
        # Calculate actual payment amounts
        quote = next((q for q in stage0_quotes if q['model'] == model), None)
        quoted_cost = quote['estimated_cost'] if quote else 0
        
        payment_amount = (llm_receives / 100) * quote_sum
        chairman_payment_amount = (chairman_pays / 100) * quote_sum
        
        payments[model] = {
            "model": model,
            "quoted_cost": quoted_cost,
            "self_eval_mcc": self_mcc,
            "chairman_decision_mcc": chairman_decision,
            "llm_final_decision_mcc": llm_decision,
            "chairman_pays_mcc": chairman_pays,
            "llm_receives_mcc": llm_receives,
            "payment_amount_usd": payment_amount,
            "chairman_payment_usd": chairman_payment_amount,
            "profit_usd": payment_amount - quoted_cost
        }
    
    # Calculate chairman's earnings
    # Chairman starts with the full pot (100% of quote_sum)
    # Then pays out to each LLM (which can exceed 100% due to penalties)
    total_chairman_pays_mcc = sum(p["chairman_pays_mcc"] for p in payments.values())
    total_llm_receives_mcc = sum(p["llm_receives_mcc"] for p in payments.values())
    
    # Chairman earnings = what they started with minus what they paid
    chairman_earnings_mcc = 100 - total_chairman_pays_mcc
    chairman_earnings_usd = (chairman_earnings_mcc / 100) * quote_sum
    
    return {
        "per_model_payments": payments,
        "total_quote_sum": quote_sum,
        "total_chairman_pays_mcc": total_chairman_pays_mcc,
        "total_paid_to_llms_mcc": total_llm_receives_mcc,
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
