"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# Model pricing - cost per million tokens (input + output average)
# These should be updated periodically from OpenRouter pricing
MODEL_COSTS = {
    "openai/gpt-5.1": 10.0,
    "google/gemini-3-pro-preview": 12.0,
    "anthropic/claude-sonnet-4.5": 15.0,
    "x-ai/grok-4": 15.0,
}

# Penalty parameter for negotiation disagreements (percentage points)
NEGOTIATION_PENALTY_T = 5.0

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
