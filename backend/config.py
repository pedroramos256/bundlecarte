"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Chairman model - fallback if API fetch fails (will use #1 ranked model from OpenRouter API)
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# Penalty parameter for negotiation disagreements (percentage points)
NEGOTIATION_PENALTY_T = 5.0

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
