"""OpenRouter API client for making LLM requests."""

import httpx
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    max_tokens: Optional[int] = 500
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens to generate (optional, for token budget control)

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }
    
    # Add max_tokens to payload if specified
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        print(f"[OPENROUTER] Querying {model} with max_tokens={max_tokens}, timeout={timeout}s")
        # Create timeout config with explicit connect and read timeouts
        timeout_config = httpx.Timeout(timeout=timeout, connect=30.0, read=timeout, write=30.0)
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            print(f"[OPENROUTER] {model} responded with status {response.status_code}")
            response.raise_for_status()

            data = response.json()
            
            # Check if response has expected structure
            if 'choices' not in data or not data['choices']:
                print(f"[OPENROUTER] ERROR: {model} response missing 'choices' field. Response: {data}")
                return None
            
            message = data['choices'][0]['message']
            content = message.get('content')
            print(f"[OPENROUTER] {model} returned content length: {len(content) if content else 0}")

            return {
                'content': content,
                'reasoning_details': message.get('reasoning_details')
            }

    except httpx.TimeoutException as e:
        print(f"[OPENROUTER] TIMEOUT querying model {model} after {timeout}s: {e}")
        return None
    except Exception as e:
        print(f"[OPENROUTER] ERROR querying model {model}: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    max_tokens_per_model: Optional[Dict[str, int]] = 1000,
    timeout: float = 240.0
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        max_tokens_per_model: Optional dict mapping model to max_tokens limit
        timeout: Request timeout in seconds (default 240s for longer responses)

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    if max_tokens_per_model:
        tasks = [
            query_model(model, messages, max_tokens=max_tokens_per_model.get(model), timeout=timeout)
            for model in models
        ]
    else:
        tasks = [query_model(model, messages, timeout=timeout) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}


async def fetch_top_models(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch top models from major AI providers via OpenRouter API.
    
    Strategy:
    - Priority providers (OpenAI, Anthropic, Google, xAI): Get most recent + most expensive = 8 models
    - Other providers: Get 2 most recent models from last 3 months
    - Total: 10 models
    
    Args:
        limit: Number of models to fetch (default 10)
        
    Returns:
        List of model dicts with 'id', 'name', 'pricing', 'context_length'
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    
    # Priority providers - get most popular and most recent from each
    priority_providers = ['openai', 'anthropic', 'google', 'x-ai']
    
    # Map of priority providers to their actual prefix patterns in model IDs
    provider_patterns = {
        'openai': 'openai/',
        'anthropic': 'anthropic/',
        'google': 'google/',
        'x-ai': 'x-ai/'
    }
    
    try:
        print(f"[OPENROUTER] Fetching models from major AI providers...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch all models from the API
            models_response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers=headers
            )
            models_response.raise_for_status()
            models_data = models_response.json()
            
            all_models = models_data.get('data', [])
            print(f"[OPENROUTER] Fetched {len(all_models)} total models")
            
            # Filter for text-to-text models with valid pricing
            filtered_models = []
            for model in all_models:
                model_id = model.get('id', '')
                
                # Check if model supports text input and text output
                modality = model.get('modality') or model.get('architecture', {}).get('modality', '')
                # Accept any modality that has text in input and text in output
                if '->' in modality:
                    input_modality, output_modality = modality.split('->', 1)
                    has_text_input = 'text' in input_modality
                    has_text_output = 'text' in output_modality
                    if not (has_text_input and has_text_output):
                        continue
                else:
                    # No modality format, skip
                    continue
                
                # Check if has valid pricing (non-zero and reasonable)
                pricing = model.get('pricing', {})
                prompt_price = pricing.get('prompt', '0')
                completion_price = pricing.get('completion', '0')
                
                # Skip if pricing is missing or zero
                if not prompt_price or not completion_price:
                    continue
                if float(prompt_price) <= 0 or float(completion_price) <= 0:
                    continue
                
                # Skip if completion cost > $50/M tokens
                completion_cost_per_m = float(completion_price) * 1_000_000
                if completion_cost_per_m > 50:
                    continue
                
                filtered_models.append(model)
            
            print(f"[OPENROUTER] Filtered to {len(filtered_models)} valid text models")
            
            # Group models by provider (normalize provider names)
            models_by_provider = {}
            for model in filtered_models:
                model_id = model.get('id', '')
                provider = model_id.split('/')[0] if '/' in model_id else ''
                
                if provider not in models_by_provider:
                    models_by_provider[provider] = []
                models_by_provider[provider].append(model)
            
            result = []
            
            # For each priority provider, get most recent and most expensive
            for provider in priority_providers:
                if provider not in models_by_provider:
                    print(f"[OPENROUTER] No models found for {provider}")
                    continue
                
                provider_models = models_by_provider[provider]
                
                # Most recent (newest creation date)
                most_recent = max(provider_models, key=lambda m: m.get('created', 0))
                
                # Most expensive (highest prompt pricing)
                most_expensive = max(provider_models, key=lambda m: float(m.get('pricing', {}).get('prompt', '0')))
                for model in [most_recent, most_expensive]:
                    if model['id'] not in [r['id'] for r in result]:
                        pricing = model.get('pricing', {})
                        prompt_cost = float(pricing.get('prompt', '0')) * 1_000_000
                        completion_cost = float(pricing.get('completion', '0')) * 1_000_000
                        
                        result.append({
                            'id': model.get('id'),
                            'name': model.get('name'),
                            'context_length': model.get('context_length'),
                            'pricing': {
                                'prompt': prompt_cost,
                                'completion': completion_cost
                            }
                        })
                        print(f"[OPENROUTER] Added {model['id']} from {provider}")
            
            # Fill remaining 2 slots with non-priority providers
            # Get most recent models from last 3 months from other providers
            import time
            three_months_ago = time.time() - (90 * 24 * 60 * 60)  # 90 days in seconds
            
            other_providers_recent = []
            for provider, models in models_by_provider.items():
                if provider not in priority_providers:
                    # Get most recent model from this provider
                    most_recent = max(models, key=lambda m: m.get('created', 0))
                    # Only include if created in last 3 months
                    if most_recent.get('created', 0) >= three_months_ago:
                        other_providers_recent.append((provider, most_recent))
            
            # Sort by creation date (newest first)
            other_providers_recent.sort(key=lambda x: x[1].get('created', 0), reverse=True)
            
            # Add exactly 2 most recent models from other providers
            for provider, model in other_providers_recent[:2]:
                if model['id'] not in [r['id'] for r in result]:
                    pricing = model.get('pricing', {})
                    prompt_cost = float(pricing.get('prompt', '0')) * 1_000_000
                    completion_cost = float(pricing.get('completion', '0')) * 1_000_000
                    
                    result.append({
                        'id': model.get('id'),
                        'name': model.get('name'),
                        'context_length': model.get('context_length'),
                        'pricing': {
                            'prompt': prompt_cost,
                            'completion': completion_cost
                        }
                    })
            print(f"[OPENROUTER] Selected {len(result)} models:")
            for i, m in enumerate(result, 1):
                ctx = m['context_length'] / 1000 if m['context_length'] else 0
                print(f"  {i}. {m['id']}: {ctx:.0f}k ctx, input=${m['pricing']['prompt']:.2f}/M, output=${m['pricing']['completion']:.2f}/M")
            
            return result
            
    except Exception as e:
        print(f"[OPENROUTER] ERROR fetching models: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []
