"""OpenRouter API client for making LLM requests."""

import httpx
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    max_tokens: Optional[int] = 1000
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
        async with httpx.AsyncClient(timeout=timeout) as client:
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
