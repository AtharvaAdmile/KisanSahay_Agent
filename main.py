#!/usr/bin/env python3
"""
main.py — FastAPI server wrapping the PMFBY AI Agent.

Provides a REST API so React Native (or any frontend) can call
the browser automation agent without running it as a CLI.

Usage:
    uvicorn main:app --reload --port 8000

Endpoints:
    POST /agent/run        — Run the agent with a FarmerProfile + optional prompt
    POST /agent/chat       — Interactive session with reasoning agent
    DELETE /agent/session/{session_id} — Close a session and cleanup browser
    GET  /health           — Liveness check
    GET  /intents          — List all supported intents
"""

import os
import sys
import asyncio
import logging
import time
from typing import Optional, Any

# ── Preserve the same sys.path logic as pmfby_agent.py ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.config.pmfby import PMFBY_CONFIG
from shared.utils.user_profile import UserProfile
from shared.agent.intent_parser import IntentParser
from shared.agent.planner import create_plan_for_intent
from shared.browser.controller import Browser
from shared.agent.executor import Executor

# Import the async run() from the CLI entry point
from pmfby_agent import run as agent_run

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("pmfby_api")

# ── Session Management ─────────────────────────────────────────────────────────
# In-memory dictionary mapped by session_id.
# Stores: {"executor": Executor, "browser": Browser, "last_activity": float, "ready_event": Event}
active_sessions: dict[str, dict] = {}

SESSION_TTL_SECONDS = 600  # 10 minutes idle before cleanup

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="PMFBY AI Agent API",
    description=(
        "REST wrapper around the PMFBY browser automation agent. "
        "Accepts a FarmerProfile (matching the React Native store) "
        "plus an optional prompt, and returns structured results."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow React Native Metro bundler and Expo dev servers ─────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # React web / Next.js
        "http://localhost:8081",    # React Native Metro bundler
        "http://localhost:19000",   # Expo Go
        "http://localhost:19001",   # Expo DevTools
        "http://localhost:19002",   # Expo DevTools (alt)
        "exp://localhost:8081",     # Expo deep-link
        "*",                        # Dev convenience — tighten in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ───────────────────────────────────────────────────────────

class FarmerProfile(BaseModel):
    """
    Mirrors the farmer data stored in the React Native app's state/store.
    All fields are optional so the frontend can send partial profiles.
    """
    # Onboarding / app preferences
    language: Optional[str] = Field(None, description="Preferred language code, e.g. 'en', 'hi', 'mr'")

    # Personal details
    full_name: Optional[str] = Field(None, description="Farmer's full name")
    mobile: Optional[str] = Field(None, description="10-digit mobile number")
    age: Optional[str] = Field(None, description="Age in years")
    gender: Optional[str] = Field(None, description="Male / Female / Other")
    caste: Optional[str] = Field(None, description="GENERAL / OBC / SC / ST")
    relationship: Optional[str] = Field(None, description="S/O, D/O, W/O, C/O")
    relative_name: Optional[str] = Field(None, description="Father / Husband name")
    aadhaar: Optional[str] = Field(None, description="12-digit Aadhaar number")

    # Address
    state: Optional[str] = Field(None, description="State name (e.g. 'Rajasthan')")
    district: Optional[str] = Field(None, description="District name")
    taluka: Optional[str] = Field(None, alias="sub_district", description="Taluka / Sub-district / Tehsil")
    village: Optional[str] = Field(None, description="Village or town name")
    pincode: Optional[str] = Field(None, description="6-digit PIN code")
    address: Optional[str] = Field(None, description="Full address text")

    # Crop details
    primary_crop: Optional[str] = Field(None, alias="crop_type", description="Primary crop name (e.g. 'wheat', 'cotton')")
    season: Optional[str] = Field(None, description="Kharif / Rabi / Zaid")
    land_size: Optional[str] = Field(None, description="Land size in hectares")
    crop_year: Optional[str] = Field(None, description="Crop year, e.g. '2025'")

    # Bank details
    bank_name: Optional[str] = Field(None, description="Bank name")
    bank_branch: Optional[str] = Field(None, description="Branch name")
    bank_state: Optional[str] = Field(None, description="Bank state")
    bank_district: Optional[str] = Field(None, description="Bank district")
    account_no: Optional[str] = Field(None, description="Bank account number")
    ifsc: Optional[str] = Field(None, description="IFSC code")

    # Portal credentials (stored in keyring on server if available)
    lms_mobile: Optional[str] = Field(None, description="Mobile registered on LMS portal")
    lms_password: Optional[str] = Field(None, description="LMS portal password")
    cropic_mobile: Optional[str] = Field(None, description="Mobile registered on CROPIC")
    cropic_password: Optional[str] = Field(None, description="CROPIC portal password")

    model_config = {"populate_by_name": True}  # allow both alias and field name


class AgentRequest(BaseModel):
    """Request body for POST /agent/run"""
    profile: FarmerProfile = Field(
        default_factory=FarmerProfile,
        description="Farmer profile — used to pre-fill forms automatically"
    )
    prompt: Optional[str] = Field(
        None,
        description=(
            "Natural language instruction for the agent. "
            "If omitted, defaults to checking eligibility for the farmer's primary crop."
        ),
    )
    headless: bool = Field(
        True,
        description="Run in headless mode (True = no visible browser window)"
    )
    verbose: bool = Field(
        False,
        description="Enable verbose debug logging"
    )


class AgentResponse(BaseModel):
    """Response body from POST /agent/run"""
    status: str = Field(..., description="'success' or 'error'")
    intent: Optional[str] = Field(None, description="Classified intent")
    results: dict[str, Any] = Field(default_factory=dict, description="Structured results from the agent")
    error: Optional[str] = Field(None, description="Error message if status == 'error'")


class ChatRequest(BaseModel):
    """Request body for POST /agent/chat"""
    session_id: Optional[str] = Field(None, description="Unique session ID. If omitted, starts a new session.")
    message: Optional[str] = Field(None, description="User's answer to the agent's previous question.")
    prompt: Optional[str] = Field(None, description="Initial prompt to start the session (only used if session_id is new).")
    profile: FarmerProfile = Field(default_factory=FarmerProfile, description="Farmer profile data.")
    forced_intent: Optional[str] = Field(None, description="Explicit intent to skip the parsing LLM.")
    headless: bool = Field(False, description="Run in headless mode (default False for testing).")


class ChatResponse(BaseModel):
    """Response body from POST /agent/chat"""
    session_id: str
    status: str = Field(..., description="'requires_input', 'ready_to_submit', 'success', or 'error'")
    question: Optional[str] = None
    options: Optional[list[str]] = None
    summary: Optional[dict[str, Any]] = None
    error: Optional[str] = None


# ── Helper: inject FarmerProfile into UserProfile ────────────────────────────

def _build_profile_from_request(farmer: FarmerProfile) -> UserProfile:
    """
    Create a temporary in-memory UserProfile populated from the API request.
    We write to a *request-scoped* temp path so parallel requests don't
    clobber each other's disk profiles.

    The profile is then picked up by run() via the config's profile_path.
    Since run() loads the profile from disk, we write it to the config path
    (the standard ~/.pmfby_agent/profile.json). For production multi-user
    deployments swap this for a per-request temp file.
    """
    config = PMFBY_CONFIG
    profile = UserProfile(
        profile_path=config.profile_path,
        sensitive_keys=config.sensitive_keys,
        keyring_service=config.keyring_service,
    )

    # Map FarmerProfile fields → UserProfile dot-notation keys
    mapping = {
        # personal
        "personal.full_name":     farmer.full_name,
        "personal.mobile":        farmer.mobile,
        "personal.age":           farmer.age,
        "personal.gender":        farmer.gender,
        "personal.caste":         farmer.caste,
        "personal.relationship":  farmer.relationship,
        "personal.relative_name": farmer.relative_name,
        "personal.aadhaar":       farmer.aadhaar,
        # address
        "address.state":          farmer.state,
        "address.district":       farmer.district,
        "address.sub_district":   farmer.taluka,
        "address.village":        farmer.village,
        "address.pincode":        farmer.pincode,
        "address.address":        farmer.address,
        # crop
        "crop.crop_name":         farmer.primary_crop,
        "crop.season":            farmer.season,
        "crop.area_ha":           farmer.land_size,
        "crop.year":              farmer.crop_year,
        # bank
        "bank.name":              farmer.bank_name,
        "bank.branch":            farmer.bank_branch,
        "bank.state":             farmer.bank_state,
        "bank.district":          farmer.bank_district,
        "bank.account_no":        farmer.account_no,
        "bank.ifsc":              farmer.ifsc,
        # portals
        "portals.lms_mobile":     farmer.lms_mobile,
        "portals.lms_password":   farmer.lms_password,
        "portals.cropic_mobile":  farmer.cropic_mobile,
        "portals.cropic_password":farmer.cropic_password,
    }

    for key, value in mapping.items():
        if value:  # only write non-empty values
            profile.set(key, str(value))

    return profile


def _build_default_prompt(farmer: FarmerProfile) -> str:
    """Generate a sensible default prompt when none is provided."""
    crop = farmer.primary_crop or "crops"
    state = farmer.state or "my state"
    season = farmer.season or "current"
    return (
        f"Explore the PMFBY site and check eligibility for {crop} "
        f"in {season} season in {state}"
    )


# ── Session Cleanup ──────────────────────────────────────────────────────────

async def _cleanup_session(session_id: str) -> None:
    """Close the browser and remove a session from active_sessions."""
    session = active_sessions.pop(session_id, None)
    if session is None:
        return
    browser = session.get("browser")
    if browser:
        try:
            await browser.close()
            log.info(f"[{session_id}] Browser closed and session cleaned up")
        except Exception as e:
            log.warning(f"[{session_id}] Error closing browser: {e}")


async def _stale_session_reaper():
    """Background task that periodically cleans up idle sessions."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        now = time.time()
        stale_ids = [
            sid for sid, data in active_sessions.items()
            if now - data.get("last_activity", now) > SESSION_TTL_SECONDS
        ]
        for sid in stale_ids:
            log.info(f"[{sid}] Session idle for >{SESSION_TTL_SECONDS}s, cleaning up")
            await _cleanup_session(sid)


@app.on_event("startup")
async def _start_reaper():
    """Start the stale session reaper on app startup."""
    asyncio.create_task(_stale_session_reaper())


# ── Endpoints ─────────────────────────────────────────────────────────────────

async def _stateful_agent_worker(
    session_id: str, prompt: str, profile_data: dict,
    headless: bool, verbose: bool, forced_intent: str = None,
    ready_event: asyncio.Event = None
):
    """Background task to run the agent with ReAct reasoning loops."""
    config = PMFBY_CONFIG
    log.info(f"[{session_id}] Starting stateful worker for prompt: {prompt}")

    browser = None
    try:
        if forced_intent:
            log.info(f"[{session_id}] Bypassing parser. Forced intent: {forced_intent}")
            intent = forced_intent
            params = {}
        else:
            parser = IntentParser(config, verbose=verbose)
            intent_result = parser.parse(prompt)
            intent = intent_result["intent"]
            params = intent_result["params"]

        plan = create_plan_for_intent(config, intent, params)

        browser = Browser(config, headless=headless, verbose=verbose)
        executor = Executor(browser, config, verbose=verbose)
        executor.set_intent(intent)

        active_sessions[session_id] = {
            "executor": executor,
            "browser": browser,
            "last_activity": time.time(),
            "results": {}
        }

        # Signal that the session is ready
        if ready_event:
            ready_event.set()

        await browser.launch()

        # Run the executor. It will block waiting on user_input_queue when yielding.
        results = await executor.execute(plan, profile_data)

        # After execution completes, push final success to the output queue
        await executor.agent_output_queue.put({
            "status": "success",
            "results": results
        })
    except Exception as e:
        log.error(f"[{session_id}] Worker failed: {e}")
        session = active_sessions.get(session_id)
        if session and "executor" in session:
            await session["executor"].agent_output_queue.put({
                "status": "error",
                "error": str(e)
            })
        # Ensure ready_event is set even on failure so the caller doesn't hang
        if ready_event and not ready_event.is_set():
            ready_event.set()
    finally:
        # Close browser on worker exit to prevent zombie Chromium processes
        if browser:
            try:
                await browser.close()
                log.info(f"[{session_id}] Browser closed in worker finally block")
            except Exception as e:
                log.warning(f"[{session_id}] Error closing browser in finally: {e}")


@app.post(
    "/agent/chat",
    response_model=ChatResponse,
    tags=["Agent", "Interactive"],
    summary="Interactive session with reasoning agent",
)
async def chat_agent(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Main endpoint for stateful chat interactions with the browser agent.
    - If `session_id` is blank, starts a new Playwright agent in the background.
    - If `session_id` exists and `message` is provided, sends the message to the agent.
    - Resolves by returning the next question (`requires_input`), the final summary (`ready_to_submit`), or `success`.
    """
    session_id = request.session_id or str(uuid.uuid4())

    # 1. Start a new session if needed
    if session_id not in active_sessions:
        prompt = request.prompt or _build_default_prompt(request.profile)
        # We convert to a dict to pass to the executor for direct mutation/reading
        profile_data = request.profile.model_dump(exclude_none=True, by_alias=True)

        # Use an asyncio.Event for synchronization instead of arbitrary sleep
        ready_event = asyncio.Event()

        task = asyncio.create_task(
            _stateful_agent_worker(
                session_id=session_id,
                prompt=prompt,
                profile_data=profile_data,
                headless=request.headless,
                verbose=True,
                forced_intent=request.forced_intent,
                ready_event=ready_event,
            )
        )

        # Wait for the worker to register in active_sessions (with timeout)
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            return ChatResponse(
                session_id=session_id,
                status="error",
                error="Session initialization timed out after 30 seconds."
            )

        if session_id not in active_sessions:
            return ChatResponse(session_id=session_id, status="error", error="Failed to start session.")

    session_data = active_sessions[session_id]
    session_data["last_activity"] = time.time()
    executor = session_data["executor"]

    # 2. Provide the user's message to the paused execution if provided
    if request.message:
        log.info(f"[{session_id}] Sending answer to queue: {request.message}")
        await executor.user_input_queue.put(request.message)

    # 3. Wait for the agent to yield its next response
    try:
        log.info(f"[{session_id}] Waiting for agent output...")
        response = await asyncio.wait_for(executor.agent_output_queue.get(), timeout=120.0)

        return ChatResponse(
            session_id=session_id,
            status=response.get("status"),
            question=response.get("question"),
            options=response.get("options"),
            summary=response.get("summary"),
            error=response.get("error")
        )
    except asyncio.TimeoutError:
        return ChatResponse(session_id=session_id, status="error", error="Agent timed out waiting for DOM or reasoning.")


@app.delete(
    "/agent/session/{session_id}",
    tags=["Agent", "Session"],
    summary="Close a session and cleanup its browser",
)
async def delete_session(session_id: str):
    """Close the browser and remove the session. Prevents zombie Chromium processes."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    await _cleanup_session(session_id)
    return {"status": "ok", "message": f"Session {session_id} cleaned up"}


@app.get("/health", tags=["Meta"])
async def health_check():
    """Liveness check — returns 200 if the server is running."""
    return {"status": "ok", "service": "PMFBY AI Agent API", "active_sessions": len(active_sessions)}


@app.get("/intents", tags=["Meta"])
async def list_intents():
    """Return all supported intents with their descriptions."""
    schema = PMFBY_CONFIG.intent_schema
    return {
        "intents": {
            name: defn.description
            for name, defn in schema.items()
        }
    }


@app.post(
    "/agent/run",
    response_model=AgentResponse,
    tags=["Agent"],
    summary="Run the PMFBY agent with a farmer profile and optional prompt",
)
async def run_agent(request: AgentRequest):
    """
    Execute the PMFBY browser automation agent.

    - **profile**: Farmer details used to pre-fill application forms automatically.
    - **prompt**: Natural language instruction. Defaults to an eligibility check for the farmer's primary crop.
    - **headless**: Whether to run the browser without a visible window (default: True).
    - **verbose**: Enable debug-level logging (default: False).

    Returns structured results including any screenshots taken and data extracted.
    """
    farmer  = request.profile
    prompt  = request.prompt or _build_default_prompt(farmer)
    headless = request.headless
    verbose  = request.verbose

    log.info(f"Agent request — prompt: '{prompt[:80]}' | headless: {headless}")

    # Write the farmer's profile to disk so run() picks it up
    try:
        _build_profile_from_request(farmer)
    except Exception as e:
        log.warning(f"Could not persist profile: {e}")

    try:
        results = await asyncio.wait_for(
            agent_run(prompt, headless=headless, verbose=verbose),
            timeout=300,   # 5 minute hard cap
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out after 5 minutes")
    except Exception as e:
        log.error(f"Agent execution error: {e}", exc_info=True)
        return AgentResponse(
            status="error",
            results={},
            error=str(e),
        )

    # Extract intent from results if the agent stored it
    intent = results.pop("intent", None)
    error  = results.get("error")

    return AgentResponse(
        status="error" if error else "success",
        intent=intent,
        results=results,
        error=error,
    )


# ── Dev server entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # Listening on 0.0.0.0 allows external connections (e.g., via your machine's IP address)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
