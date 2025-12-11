"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uuid
import json
import asyncio
import traceback

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
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Global exception handler to ensure CORS headers are always present
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[ERROR] Unhandled exception: {exc}")
    print(f"[ERROR] Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__}
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
    status: str = "active"
    current_stage: int = None
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
    print(f"\n{'='*80}")
    print(f"[ENDPOINT] Received request for stage0 quotes")
    print(f"[ENDPOINT] Content: {request.content}")
    print(f"{'='*80}\n")
    try:
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
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
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

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage0=results.get("stage0_quotes", []),
        stage1=results.get("stage1_answers", []),
        stage2=results.get("stage2_chairman_eval", {}),
        stage3=results.get("stage3_self_evals", []),
        stage4=results.get("stage4_chairman_decision", {}),
        stage5=results.get("stage5_llm_finals", []),
        stage6=results.get("stage6_payments", [])
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
            # Check if we're resuming an in-progress conversation
            # (check BEFORE adding user message to avoid duplicates)
            in_progress_message = None
            user_content = request.content
            
            if conversation["messages"] and conversation["messages"][-1]["role"] == "assistant":
                # Check if it's incomplete
                last_msg = conversation["messages"][-1]
                is_incomplete = any(last_msg.get(f"stage{i}") is None for i in range(1, 8))
                if is_incomplete:
                    in_progress_message = last_msg
                    # Get the user message that started this conversation thread
                    # Find the last user message before this assistant message
                    for i in range(len(conversation["messages"]) - 2, -1, -1):
                        if conversation["messages"][i]["role"] == "user":
                            user_content = conversation["messages"][i]["content"]
                            break
            
            # If not resuming, add user message and create new assistant message
            if in_progress_message is None:
                storage.add_user_message(conversation_id, user_content)
                in_progress_message = storage.get_or_create_in_progress_message(conversation_id)
            
            resume_from_stage = 0
            
            # Find which stage to resume from (first incomplete stage)
            for stage_idx in range(7):
                stage_key = f"stage{stage_idx + 1}"
                if in_progress_message.get(stage_key) is None:
                    resume_from_stage = stage_idx
                    break
            else:
                # All stages complete - this shouldn't happen but handle it
                resume_from_stage = 7
            
            # If resuming, emit already-completed stages
            if resume_from_stage > 0:
                for stage_idx in range(resume_from_stage):
                    stage_key = f"stage{stage_idx + 1}"
                    stage_data = in_progress_message.get(stage_key)
                    if stage_data is not None:
                        yield f"data: {json.dumps({'type': f'stage{stage_idx}_complete', 'data': stage_data}, ensure_ascii=False)}\n\n"
            
            # Set status to processing at resume point
            storage.update_conversation_status(conversation_id, "processing", resume_from_stage)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(user_content))

            # Import auction stages
            from .council import (
                stage0_collect_quotes, stage1_collect_responses, stage2_evaluate_mccs,
                stage3_llm_self_evaluation, stage4_chairman_final_decision,
                stage5_llm_final_acceptance, stage6_calculate_final_payments
            )

            # Load saved data for resume
            stage0_quotes = in_progress_message.get('stage1')
            stage1_results = in_progress_message.get('stage2')
            stage2_chairman_eval = in_progress_message.get('stage3')
            stage3_self_evals = in_progress_message.get('stage4')
            stage4_chairman_decision = in_progress_message.get('stage5')
            stage5_llm_finals = in_progress_message.get('stage6')

            # Stage 0: Token quotes
            if resume_from_stage <= 0:
                yield f"data: {json.dumps({'type': 'stage0_start'}, ensure_ascii=False)}\n\n"
                stage0_quotes = await stage0_collect_quotes(user_content)
                storage.save_stage_output(conversation_id, 0, stage0_quotes)
                yield f"data: {json.dumps({'type': 'stage0_complete', 'data': stage0_quotes}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 1)

            max_tokens_per_model = {q['model']: q['quoted_tokens'] for q in stage0_quotes}

            # Stage 1: Collect responses
            if resume_from_stage <= 1:
                yield f"data: {json.dumps({'type': 'stage1_start'}, ensure_ascii=False)}\n\n"
                stage1_results = await stage1_collect_responses(user_content, max_tokens_per_model)
                storage.save_stage_output(conversation_id, 1, stage1_results)
                yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 2)

            if not stage1_results:
                storage.update_conversation_status(conversation_id, "error", None)
                yield f"data: {json.dumps({'type': 'error', 'message': 'All models failed to respond'}, ensure_ascii=False)}\n\n"
                return

            # Stage 2: Chairman evaluation
            if resume_from_stage <= 2:
                yield f"data: {json.dumps({'type': 'stage2_start'}, ensure_ascii=False)}\n\n"
                stage2_chairman_eval = await stage2_evaluate_mccs(user_content, stage0_quotes, stage1_results)
                storage.save_stage_output(conversation_id, 2, stage2_chairman_eval)
                yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_chairman_eval}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 3)

            # Stage 3: LLM self-evaluation
            if resume_from_stage <= 3:
                yield f"data: {json.dumps({'type': 'stage3_start'}, ensure_ascii=False)}\n\n"
                stage3_self_evals = await stage3_llm_self_evaluation(user_content, stage0_quotes, stage1_results, stage2_chairman_eval)
                storage.save_stage_output(conversation_id, 3, stage3_self_evals)
                yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_self_evals}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 4)

            # Stage 4: Chairman final decision
            if resume_from_stage <= 4:
                yield f"data: {json.dumps({'type': 'stage4_start'}, ensure_ascii=False)}\n\n"
                stage4_chairman_decision = await stage4_chairman_final_decision(user_content, stage0_quotes, stage1_results, stage2_chairman_eval, stage3_self_evals)
                storage.save_stage_output(conversation_id, 4, stage4_chairman_decision)
                yield f"data: {json.dumps({'type': 'stage4_complete', 'data': stage4_chairman_decision}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 5)

            # Stage 5: LLM final acceptance
            if resume_from_stage <= 5:
                yield f"data: {json.dumps({'type': 'stage5_start'}, ensure_ascii=False)}\n\n"
                stage5_llm_finals = await stage5_llm_final_acceptance(user_content, stage0_quotes, stage1_results, stage2_chairman_eval, stage3_self_evals, stage4_chairman_decision)
                storage.save_stage_output(conversation_id, 5, stage5_llm_finals)
                yield f"data: {json.dumps({'type': 'stage5_complete', 'data': stage5_llm_finals}, ensure_ascii=False)}\n\n"
                storage.update_conversation_status(conversation_id, "processing", 6)

            # Stage 6: Calculate payments
            if resume_from_stage <= 6:
                yield f"data: {json.dumps({'type': 'stage6_start'}, ensure_ascii=False)}\n\n"
                stage6_payments = stage6_calculate_final_payments(stage0_quotes, stage3_self_evals, stage4_chairman_decision, stage5_llm_finals)
                storage.save_stage_output(conversation_id, 6, stage6_payments)
                yield f"data: {json.dumps({'type': 'stage6_complete', 'data': stage6_payments}, ensure_ascii=False)}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}}, ensure_ascii=False)}\n\n"

            # Mark conversation as completed
            storage.update_conversation_status(conversation_id, "completed", None)

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            # Mark conversation as error
            storage.update_conversation_status(conversation_id, "error", None)
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
