"""JSON-based storage for conversations."""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "status": "active",
        "current_stage": None,
        "messages": []
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        return json.load(f)


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    conversations = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(DATA_DIR, filename)
            with open(path, 'r') as f:
                data = json.load(f)
                # Return metadata only
                conversations.append({
                    "id": data["id"],
                    "created_at": data["created_at"],
                    "title": data.get("title", "New Conversation"),
                    "message_count": len(data["messages"])
                })

    # Sort by creation time, newest first
    conversations.sort(key=lambda x: x["created_at"], reverse=True)

    return conversations


def add_user_message(conversation_id: str, content: str):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage0: List[Dict[str, Any]] = None,
    stage1: List[Dict[str, Any]] = None,
    stage2: Dict[str, Any] = None,
    stage3: List[Dict[str, Any]] = None,
    stage4: Dict[str, Any] = None,
    stage5: List[Dict[str, Any]] = None,
    stage6: List[Dict[str, Any]] = None
):
    """
    Add an assistant message with all 7 auction stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage0: Token budget quotes (Stage 1 in UI)
        stage1: LLM responses (Stage 2 in UI)
        stage2: Chairman evaluation with MCCs (Stage 3 in UI)
        stage3: LLM self-evaluations (Stage 4 in UI)
        stage4: Chairman final decisions (Stage 5 in UI)
        stage5: LLM final acceptance (Stage 6 in UI)
        stage6: Final payments (Stage 7 in UI)
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage0 or [],  # Token quotes
        "stage2": stage1 or [],  # LLM responses
        "stage3": stage2 or {},  # Chairman evaluation
        "stage4": stage3 or [],  # LLM self-evaluations
        "stage5": stage4 or {},  # Chairman final decisions
        "stage6": stage5 or [],  # LLM final acceptance
        "stage7": stage6 or []   # Final payments
    })

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def update_conversation_status(conversation_id: str, status: str, current_stage: Optional[int] = None):
    """
    Update the status and current stage of a conversation.

    Args:
        conversation_id: Conversation identifier
        status: Status (e.g., 'active', 'processing', 'completed', 'error')
        current_stage: Current stage being processed (0-6) or None if completed
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["status"] = status
    conversation["current_stage"] = current_stage
    save_conversation(conversation)


def get_or_create_in_progress_message(conversation_id: str) -> Dict[str, Any]:
    """
    Get the last assistant message if it exists and is incomplete, or create a new one.
    This allows resuming interrupted conversations.

    Args:
        conversation_id: Conversation identifier

    Returns:
        The in-progress assistant message dict
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Check if last message is an incomplete assistant message
    if conversation["messages"] and conversation["messages"][-1]["role"] == "assistant":
        return conversation["messages"][-1]
    
    # Create new assistant message
    message = {
        "role": "assistant",
        "stage1": None,  # Token quotes
        "stage2": None,  # LLM responses
        "stage3": None,  # Chairman evaluation
        "stage4": None,  # LLM self-evaluations
        "stage5": None,  # Chairman final decisions
        "stage6": None,  # LLM final acceptance
        "stage7": None   # Final payments
    }
    conversation["messages"].append(message)
    save_conversation(conversation)
    return message


def save_stage_output(conversation_id: str, stage_num: int, data: Any):
    """
    Save a specific stage's output to the last assistant message.
    Creates the assistant message if it doesn't exist.

    Args:
        conversation_id: Conversation identifier
        stage_num: Stage number (0-6 for backend stages)
        data: Stage output data
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Get or create in-progress message
    if conversation["messages"] and conversation["messages"][-1]["role"] == "assistant":
        message = conversation["messages"][-1]
    else:
        message = {
            "role": "assistant",
            "stage1": None,
            "stage2": None,
            "stage3": None,
            "stage4": None,
            "stage5": None,
            "stage6": None,
            "stage7": None
        }
        conversation["messages"].append(message)

    # Map backend stage (0-6) to UI stage (1-7)
    stage_key = f"stage{stage_num + 1}"
    message[stage_key] = data
    
    save_conversation(conversation)
