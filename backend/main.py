"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import json
import asyncio

from . import storage
from .council import (
    run_full_council, generate_conversation_title, 
    stage0_collect_quotes  # New auction mechanism
)

app = FastAPI(title="LLM Council API")

# Enable CORS for production and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bundlecarte.com",
        "https://www.bundlecarte.com",
        "http://localhost:5173",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.post("/api/test/stage0-quotes")
async def test_stage0_quotes(request: SendMessageRequest):
    """
    Test endpoint for Stage 0: Token Budget Quoting.
    Returns quotes from all LLMs for a given prompt.
    """
    quotes = await stage0_collect_quotes(request.content)
    
    # Calculate total cost
    total_cost = sum(q["estimated_cost"] for q in quotes)
    
    return {
        "stage": "stage0_quotes",
        "prompt": request.content,
        "quotes": quotes,
        "total_estimated_cost": total_cost,
        "currency": "USD"
    }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 6-stage auction council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 6-stage auction council process
    results = await run_full_council(request.content)

    # Add assistant message with all stages (simplified for storage)
    storage.add_assistant_message(
        conversation_id,
        results.get("stage1_answers", []),
        [],  # No stage2 in new format
        {
            "model": results["stage2_chairman_eval"]["model"],
            "response": results["stage2_chairman_eval"]["aggregated_answer"]
        }
    )

    # Return the complete response with all auction stages
    return results


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 6-stage auction council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Import auction stages
            from .council import (
                stage0_collect_quotes, stage1_collect_responses, stage2_evaluate_mccs,
                stage3_llm_self_evaluation, stage4_chairman_final_decision,
                stage5_llm_final_acceptance, stage6_calculate_final_payments
            )

            # Stage 0: Token quotes
            yield f"data: {json.dumps({'type': 'stage0_start'}, ensure_ascii=False)}\n\n"
            stage0_quotes = await stage0_collect_quotes(request.content)
            yield f"data: {json.dumps({'type': 'stage0_complete', 'data': stage0_quotes}, ensure_ascii=False)}\n\n"

            max_tokens_per_model = {q['model']: q['quoted_tokens'] for q in stage0_quotes}

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'}, ensure_ascii=False)}\n\n"
            stage1_results = await stage1_collect_responses(request.content, max_tokens_per_model)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results}, ensure_ascii=False)}\n\n"

            if not stage1_results:
                yield f"data: {json.dumps({'type': 'error', 'message': 'All models failed to respond'}, ensure_ascii=False)}\n\n"
                return

            # Stage 2: Chairman evaluation
            yield f"data: {json.dumps({'type': 'stage2_start'}, ensure_ascii=False)}\n\n"
            stage2_chairman_eval = await stage2_evaluate_mccs(request.content, stage0_quotes, stage1_results)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_chairman_eval}, ensure_ascii=False)}\n\n"

            # Stage 3: LLM self-evaluation
            yield f"data: {json.dumps({'type': 'stage3_start'}, ensure_ascii=False)}\n\n"
            stage3_self_evals = await stage3_llm_self_evaluation(request.content, stage0_quotes, stage1_results, stage2_chairman_eval)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_self_evals}, ensure_ascii=False)}\n\n"

            # Stage 4: Chairman final decision
            yield f"data: {json.dumps({'type': 'stage4_start'}, ensure_ascii=False)}\n\n"
            stage4_chairman_decision = await stage4_chairman_final_decision(request.content, stage0_quotes, stage1_results, stage2_chairman_eval, stage3_self_evals)
            yield f"data: {json.dumps({'type': 'stage4_complete', 'data': stage4_chairman_decision}, ensure_ascii=False)}\n\n"

            # Stage 5: LLM final acceptance
            yield f"data: {json.dumps({'type': 'stage5_start'}, ensure_ascii=False)}\n\n"
            stage5_llm_finals = await stage5_llm_final_acceptance(request.content, stage0_quotes, stage1_results, stage2_chairman_eval, stage3_self_evals, stage4_chairman_decision)
            yield f"data: {json.dumps({'type': 'stage5_complete', 'data': stage5_llm_finals}, ensure_ascii=False)}\n\n"

            # Stage 6: Calculate payments
            yield f"data: {json.dumps({'type': 'stage6_start'}, ensure_ascii=False)}\n\n"
            stage6_payments = stage6_calculate_final_payments(stage0_quotes, stage3_self_evals, stage4_chairman_decision, stage5_llm_finals)
            yield f"data: {json.dumps({'type': 'stage6_complete', 'data': stage6_payments}, ensure_ascii=False)}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}}, ensure_ascii=False)}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                [],
                {
                    "model": stage2_chairman_eval["model"],
                    "response": stage2_chairman_eval["aggregated_answer"]
                }
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            # Send error event
            error_msg = str(e).replace('\n', ' ').replace('\r', ' ')
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
