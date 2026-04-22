# ADAM — Detailed Feature Specifications

## Spec 1 — 3D Model (Three.js)

### Current State
- Three.js r128 (CDN), `GLTFLoader`, Mixamo Xbot (`.glb`) loaded from `/static/models/`
- Bone mapping: 22 named bones stripped of `mixamorig` prefix, rest quaternions captured at load
- Animation: per-frame linear interpolation between bracketing keyframes (`lerpBoneRotations`)
- Camera: manual spherical orbit (mouse drag + scroll), no `OrbitControls` dependency
- Lighting: ambient + directional key light + rim + purple fill point light

### Gaps / Issues
- Three.js r128 is from 2021 — no `WebGPURenderer`, no `AnimationMixer` integration, missing modern `DRACO` compression support
- Bone mapping is string-match only; if the `.glb` uses a different naming convention the model silently breaks (already handled with `mixamorig` strip, but fragile)
- `lerp` on Euler components instead of `slerp` on quaternions — produces gimbal artifacts on large rotations
- No easing curves (all linear), no blend between running motion and incoming new motion
- No loading state / progress bar — model load failure is silent in UI unless console open
- Pixel ratio not capped — on 4K screens this is a performance problem
- **[ISSUE] No gravity** — model floats; no ground constraint, feet clip through or hover above the floor
- **[ISSUE] Inaccurate / unrealistic animation** — Euler lerp produces unnatural arcs, no secondary motion, timing feels mechanical

### Specification

#### 1.1 Renderer & Scene
| Property | Value |
|---|---|
| Three.js version | `>=0.160` (ES module import map, no CDN globals) |
| Renderer | `WebGLRenderer` with `antialias: true`, `outputColorSpace: SRGBColorSpace` |
| Pixel ratio | `Math.min(window.devicePixelRatio, 2)` |
| Tone mapping | `ACESFilmicToneMapping`, exposure `1.0` |
| Shadows | `PCFSoftShadowMap` on key light only |

#### 1.2 Model Loading
- Format: **GLB** (binary GLTF) with optional Draco compression (loader: `DRACOLoader` pointed at `/static/draco/`)
- Bone discovery: traverse `SkinnedMesh.skeleton.bones` — authoritative, not scene graph traversal
- Prefix normalisation: strip `mixamorig:`, `mixamorig`, `Bip01_` variants via regex `/^(mixamorig[: ]?|Bip01_)/`
- Store `{ bone, restQuaternion }` per mapped bone name
- Emit a `model:loaded` custom event with mapped count; UI shows progress overlay during load

#### 1.3 Animation Engine
| Concern | Approach |
|---|---|
| Interpolation | `Quaternion.slerp()` between rest×offsetA and rest×offsetB — no Euler lerp |
| Easing | Cubic in-out (`smoothstep`) on segment `t` — configurable per keyframe via optional `"easing"` field |
| Motion blending | On new motion arrival, capture current bone state as synthetic keyframe 0 and cross-fade over `blendDuration` (default 150 ms) |
| Loop | Seamless: last keyframe slerped back to KF0 during final segment |
| Idle | Default idle breathing animation (procedural, 4 s loop) plays when no active motion |

#### 1.3a Gravity & Ground Constraint _(fixes: no gravity)_
Three.js has no physics engine and none should be added — gravity is **simulated at the animation layer**:

- The floor is fixed at `y = 0`. The model's root (`Hips`) rests at its natural loaded height.
- **Foot planting**: after applying bone rotations each frame, run a simple two-bone IK pass on each leg (`UpLeg → Leg → Foot`) to pin the planted foot's ankle to `y = 0` when the keyframe data indicates a grounded pose (determined by a `"grounded": true` flag on the keyframe, set by the LLM via prompt instruction).
- **Hips settle**: if both feet are grounded, the Hips y-position is kept at the loaded rest height. If a keyframe lifts the model (jump), the Hips y offset is animated by the keyframe `"hipsY"` optional field (metres above rest, default 0).
- **No falling off the floor**: clamp Hips `y ≥ restHipsY - 0.05` at all times.
- This is purely a client-side post-processing step in the render loop — no server changes needed.

```js
// pseudocode — runs after slerp in tickAnimation()
if (kf.grounded !== false) {
  groundFoot('LeftFoot', 'LeftLeg', 'LeftUpLeg');
  groundFoot('RightFoot', 'RightLeg', 'RightUpLeg');
}
```

#### 1.3b Realistic Animation Quality _(fixes: inaccurate / non-human movement)_
Poor animation realism has two root causes: bad interpolation and bad LLM output. Fix both:

**Client-side (interpolation)**
- Replace all Euler lerp with `Quaternion.slerp()` (already in 1.3 above — this is the single highest-impact change)
- Use **ease-in-out** (`smoothstep`) as the default easing on every segment — this alone makes motion feel less robotic
- Apply a lightweight **follow-through** pass: spine and head bones lag behind their parent by one frame multiplied by a small damping factor (`0.15`) — gives natural weight

**Prompt-side (LLM output quality)**
Add a `BIOMECHANICS RULES` section to the system prompt (see Spec 2.6) enforcing:
- Counter-rotation: when the right arm swings forward, the left arm swings back and the spine twists slightly opposite
- Weight shift: walking and turning shifts the Hips laterally over the support leg
- Anticipation: fast motions (punch, jump) include a small wind-up keyframe 80–120 ms before the peak
- Follow-through: fast motions have a small overshoot keyframe after the peak before settling
- Spine never bends without involving Spine1 and Spine2 (distribute across chain)
- Minimum 4 keyframes for any motion lasting > 0.5 s

#### 1.4 Bone Offset Schema (unchanged, clarified)
```jsonc
{
  "name": "LeftArm",
  "rotation": { "x": 0, "y": 0, "z": 130 }  // degrees, XYZ Euler, offset from T-pose
}
```
Conversion: `Euler(degToRad(x), degToRad(y), degToRad(z), 'XYZ')` → `Quaternion` → multiply onto rest quaternion.

#### 1.5 Camera & Controls
- Replace manual spherical orbit with `OrbitControls` (bundled, not CDN) — proper touch support, damping
- Default target: `(0, 1, 0)` (pelvis height), min distance `1.2 m`, max distance `6 m`
- Clamp polar angle: `[5°, 85°]` — prevents looking from below floor
- Preset camera buttons: Front / Side / Free (current)

#### 1.6 UI Improvements
- FPS counter: keep, add frame-time (`ms`) tooltip
- Keyframe counter: `KF 2/5 · 0.42 s` format
- Motion label: show description + total duration + loop indicator
- Loading overlay: spinner + `"Loading model… 64%"` (GLTFLoader `onProgress` callback)
- Error overlay: shown if model 404s or parse fails, with retry button

---

## Spec 2 — LLM Motor Cortex Intelligence

### Current State
- `litellm.completion()` called synchronously (blocking async route), no streaming
- System prompt built once at import time from `SKELETON_MAP`
- `LLM_STREAM` env var exists but is ignored
- No retry on malformed JSON
- No validation of output against bone ranges or schema

### Gaps / Issues
- Blocking `litellm.completion()` inside an `async` route starves the event loop (should use `asyncio.to_thread`)
- A single malformed JSON response fails the whole request with no retry
- No schema validation — LLM can hallucinate bone names or out-of-range values that silently produce bad animations
- `max_tokens=2048` may be insufficient for complex multi-bone, multi-keyframe motions
- `temperature` not set — defaults vary per provider
- No structured output enforcement (e.g. JSON mode / response schema)
- **[ISSUE] High latency** — blocking LLM call + no streaming means user waits 3–8 s with no feedback before animation starts
- **[ISSUE] Rate limit hits** — every user message sends the full conversation + full system prompt to the LLM; no caching, no debounce

### Specification

#### 2.1 LLM Call Interface
```
complete(conversation: list[dict]) → AnimationResult
```
- Run in `asyncio.to_thread(litellm.completion, ...)` — never blocks the event loop
- Parameters: `temperature=0.4`, `max_tokens=4096`, `response_format={"type": "json_object"}` (where provider supports it)
- Streaming: honour `LLM_STREAM=true` — use `litellm.acompletion` with `stream=True`, accumulate chunks, parse when `[DONE]` received; send `{"type": "token", "delta": "..."}` frames over WS for UI feedback

#### 2.1a Latency Reduction _(fixes: high latency)_
Three targeted changes, lowest complexity first:

1. **Stream by default** — set `LLM_STREAM=true` as the recommended default. The client begins animation as soon as the first two keyframes are parsed from the stream (incremental JSON parse). This moves perceived latency from `[LLM done]` to `[first tokens arrive]` — typically 600–900 ms earlier.

2. **Motion cache** — maintain an in-process `dict[str, MotionPlan]` keyed by `sha256(command.strip().lower())[:16]`. On a cache hit, skip the LLM call entirely and reply in < 5 ms. Cache is populated after each successful call. Capacity: 50 entries (LRU eviction). Enabled by default, disable with `MOTION_CACHE=false`.
   - Cache is per-process and resets on restart — no persistence needed
   - Only exact-match commands are cached ("wave your right hand" ≠ "Wave your right hand" → normalise to lowercase)

3. **Async non-blocking** — `asyncio.to_thread` wrapping `litellm.completion` is mandatory (already in 2.1). Without this the WS loop is blocked and the `ack` frame is never sent until the LLM returns.

#### 2.1b Rate Limit Management _(fixes: fast rate limit hit)_
Rate limits are hit because each request sends the full system prompt + full history. Three mitigations:

1. **Trim context** — use the rolling-window context from Spec 3.3 (`MAX_HISTORY_TOKENS = 6000`). Never send more than the last N messages that fit within budget. The system prompt itself is ~1 200 tokens; leave the remaining budget for history.

2. **Client-side debounce** — the frontend debounces rapid sends: if the user submits a command while an LLM call is in-flight, queue it and send only after the current call resolves. Maximum queue depth: 1 (discard older pending command). This prevents a burst of 5 clicks from firing 5 API calls.

3. **Exponential backoff on 429** — in `llm.py`, catch `litellm.RateLimitError`, wait `min(2^attempt * 1s, 16s)`, retry up to 3 times before returning an error to the client. Log the backoff so the user sees `"Rate limited — retrying in 2 s"` in the command log.

```python
async def complete_with_retry(conversation, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await _complete(conversation)
        except litellm.RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = min(2 ** attempt, 16)
            await asyncio.sleep(wait)
```

#### 2.2 Output Schema (formal)
```jsonc
{
    "animations": [
        {
            "description": string,           // ≤ 60 chars, human-readable label
            "keyframes": [
                {
                    "time": number,              // seconds ≥ 0, keyframe 0 must be time=0
                    "easing": "linear"|"ease-in-out",  // optional, default ease-in-out
                    "bones": [
                        { "name": BoneName, "rotation": { "x": number, "y": number, "z": number } }
                    ]
                }
            ],
            "loop": boolean,
            "totalDuration": number          // seconds > 0
        }
    ]
}
```

#### 2.3 Output Validation Pipeline
On each LLM response, before sending to client:

1. **Code fence strip** — existing regex (keep)
2. **JSON parse** — on failure: retry once with `"Your previous response was not valid JSON. Return only the JSON object."` appended
3. **Schema validation** — top-level Pydantic model `AnimationResult` with `animations.length >= 1`, and each `MotionPlan` constrained such that:
    - `keyframes` must have ≥ 2 entries
    - `keyframes[0].time == 0`
    - All `bones[].name` must be in `KNOWN_BONES`
    - All rotation values clamped to bone's declared range (warn but don't fail)
    - `totalDuration > 0`
4. **On validation failure after retry** → return `{"ok": false, "error": "...", "raw": ...}`

#### 2.4 Pydantic Models
```python
class BoneRotation(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

class BoneKeyframe(BaseModel):
    name: str
    rotation: BoneRotation

class Keyframe(BaseModel):
    time: float
    bones: list[BoneKeyframe]
    easing: Literal["linear", "ease-in-out"] = "ease-in-out"

class MotionPlan(BaseModel):
    description: str
    keyframes: list[Keyframe]
    loop: bool = False
    totalDuration: float

class AnimationResult(BaseModel):
    animations: list[MotionPlan]
```

#### 2.5 Provider Configuration
| Env var | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | Passed to litellm model string |
| `LLM_MODEL` | `gemini/gemini-2.0-flash` | Full litellm model identifier |
| `LLM_API_KEY` | — | Required |
| `LLM_BASE_URL` | — | For local/proxy endpoints |
| `LLM_STREAM` | `false` | Enable streaming tokens |
| `LLM_TEMPERATURE` | `0.4` | New — expose tuning without code changes |
| `LLM_MAX_TOKENS` | `4096` | New — increase from 2048 |

#### 2.6 System Prompt Improvements
- Add explicit JSON-mode instruction at the top: `"Respond with ONLY a valid JSON object. No prose, no markdown, no code fences."`
- Add a `"PREVIOUS MOTION"` section injected dynamically: when conversation history contains prior assistant responses, extract the last motion's `description` and append `"The robot is currently performing: <desc>. Your keyframe 0 should transition smoothly from this pose."` This gives the LLM physical continuity context.
- Add the following **BIOMECHANICS RULES** block to the system prompt to enforce realistic human motion _(fixes: inaccurate animation)_:

```
━━━ BIOMECHANICS RULES (mandatory) ━━━
1. COUNTER-ROTATION: when right arm swings forward, left arm swings back; spine twists
   slightly in the opposite direction of the leading limb.
2. WEIGHT SHIFT: during walking, turning, or lateral moves, shift Hips z/x over the
   support leg (±5–12 degrees).
3. ANTICIPATION: for fast motions (punch, kick, jump), include a small wind-up keyframe
   80–120 ms before the peak. E.g. Hips compress slightly before a jump.
4. FOLLOW-THROUGH: after the peak of a fast motion, add a small overshoot keyframe
   (30–60 ms) before settling to the hold pose.
5. SPINE CHAIN: never rotate Spine alone. Distribute bending across Spine + Spine1 +
   Spine2 (roughly 40% / 35% / 25% of total angle).
6. GROUNDED POSES: set "grounded": true on any keyframe where both feet are on the
   floor. Set "grounded": false on airborne keyframes (jumps, kicks).
7. MINIMUM KEYFRAMES: any motion longer than 0.5 s must have ≥ 4 keyframes.
8. REALISTIC TIMING: use muscle-group timing — upper body leads lower body by 1–2
   keyframe intervals in throwing/punching motions.
```

- Add `"grounded"` as an optional boolean field to the `Keyframe` schema (default `true`). Used by the client for foot planting (see Spec 1.3a).

#### 2.7 Agentic Orchestration (LLM-First, No Hardcoded Motions)
ADAM remains LLM-first for motion generation. "Agentic" behavior should focus on orchestration around the LLM, not replacing generation with hardcoded motion templates.

Principles:
- All natural-language motion commands are generated by the LLM.
- Keep deterministic logic limited to infrastructure concerns: queueing, retries, context trimming, caching, validation, and transport resilience.
- Avoid hand-authored motion plans in runtime command routing; this prevents brittle behavior and preserves expressiveness.

What stays agentic:
- Queue depth-1 command scheduling in WebSocket loop.
- Motion cache for repeated exact commands.
- Prompt caching where provider supports it.
- Structured validation + repair retry on malformed JSON.

Why this is best for ADAM:
- Keeps core value proposition intact: LLM-generated animation.
- Avoids maintenance burden of expanding and tuning a template library.
- Prevents mismatch between user phrasing and hardcoded regex rules.

---

## Spec 3 — History & Memory

### Current State
- `AppState` holds `sessions: dict[str, Session]` and `active_session_id`
- `Session.messages: list[dict]` holds the raw `{role, content}` conversation
- Entire history is in-memory — lost on restart
- Single global `app_state` in `routes.py` — all WebSocket connections share one session
- `POST /api/command` does not use history at all
- No session management UI or API — no way to start a fresh session or review past ones

### Gaps / Issues
- In-memory only: restart = lost context
- One shared session for all clients — multiple browser tabs corrupt each other's history
- No token budget management — long conversations will exceed LLM context window
- No way to name, delete, or switch sessions
- History is raw `list[dict]` with full LLM JSON in `content` — expensive to re-send, wasteful of context

### Specification

#### 3.1 Session Scope
Each WebSocket connection gets its own session, not a shared global:
```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session = Session(id=generate_id())
    # session lives and dies with this connection
```
Sessions are identified by a UUID. The client receives `{"type": "session", "id": "..."}` on connect.

#### 3.2 Persistence Layer
Abstract behind a `HistoryStore` protocol with two implementations:

**`MemoryStore`** (default, current behaviour)
```python
class MemoryStore:
    _store: dict[str, list[Message]] = {}
```

**`FileStore`** (production default when `HISTORY_DIR` is set)
- Each session stored as `{HISTORY_DIR}/{session_id}.jsonl`
- Each line is a `Message` JSON object, appended on write
- On session restore: read all lines, replay into memory

```python
@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str                     # user: raw text; assistant: motion description only
    motion_summary: str | None       # assistant: description field from MotionPlan
    timestamp: float                 # unix time
    token_estimate: int              # rough len(content) // 4
```

> **Key design decision**: store only the `description` string (not the full JSON) in the assistant turn that goes into the LLM context. The full JSON is stored in `motion_summary` for UI/replay but not re-sent to the LLM. This reduces context token usage by ~90%.

#### 3.3 Context Window Management
Before each LLM call, build `conversation_history` with a rolling window:
```python
MAX_HISTORY_TOKENS = 6000  # configurable via env HISTORY_MAX_TOKENS

def build_context(messages: list[Message]) -> list[dict]:
    budget = MAX_HISTORY_TOKENS
    result = []
    for msg in reversed(messages):
        if msg.token_estimate > budget:
            break
        budget -= msg.token_estimate
        result.append({"role": msg.role, "content": msg.content})
    return list(reversed(result))
```

#### 3.4 Session API
New REST endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/sessions` | List session IDs + metadata (start time, message count) |
| `GET` | `/api/sessions/{id}` | Full session history (messages + motion summaries) |
| `DELETE` | `/api/sessions/{id}` | Delete session and backing file |
| `POST` | `/api/sessions/{id}/reset` | Clear messages, keep session ID |

#### 3.5 UI Session Controls
- "New session" button in panel header — sends `{"type": "new_session"}` over WS, server creates fresh session, replies with new session ID
- Session ID shown in footer in small muted text
- Log scroll-back shows full session history on reconnect (server replays `{"type": "history", "entries": [...]}` on connect)

---

## Spec 4 — Realtime Communication

### Current State
- WebSocket `/ws`: full-duplex, auto-reconnect (3 s), session-scoped conversation
- Client sends `{"command": "..."}`, server replies `{"type": "thinking"}` then `{"type": "motion", ...}` or `{"type": "error", ...}`
- REST `POST /api/command`: stateless, synchronous, no streaming
- No heartbeat / ping-pong — connection can stall silently
- No message queue — if LLM is slow and user sends again, second command overwrites first
- No acknowledgement / message ID — client can't correlate responses to requests

### Gaps / Issues
- Blocking LLM call in the WS loop means the server cannot accept a second command while one is in-flight (single-threaded per connection)
- No backpressure — rapid sends pile up
- No ping/pong keepalive — proxies (nginx, Cloudflare) will close idle connections after 60–90 s
- Error messages leak internal exception text to the client
- `wss://` auto-detection is correct but not tested with `X-Forwarded-Proto` headers (reverse proxy)
- **[ISSUE] Frequent WS disconnection** — no keepalive; proxy idle timeout (typically 60–90 s) silently drops the connection; client only notices when the next send fails

### Specification

#### 4.1 Message Protocol (versioned)

All frames carry a `v` (version) and `id` field:

**Client → Server**
```jsonc
{ "v": 1, "id": "uuid4", "type": "command", "command": "wave your right hand" }
{ "v": 1, "id": "uuid4", "type": "ping" }
{ "v": 1, "id": "uuid4", "type": "new_session" }
{ "v": 1, "id": "uuid4", "type": "reset_pose" }
```

**Server → Client**
```jsonc
{ "v": 1, "ref": "uuid4", "type": "ack" }                     // command received
{ "v": 1, "ref": "uuid4", "type": "thinking" }                // LLM call started
{ "v": 1, "ref": "uuid4", "type": "token", "delta": "..." }   // streaming chunk
{ "v": 1, "ref": "uuid4", "type": "motion", "motion": {...} } // final motion
{ "v": 1, "ref": "uuid4", "type": "error", "code": "LLM_PARSE_ERROR", "message": "..." }
{ "v": 1, "type": "session", "id": "...", "history": [...] }  // on connect
{ "v": 1, "type": "pong" }
```

`ref` echoes the client `id` so the frontend can correlate responses to requests.

#### 4.2 Concurrency & Queuing
- Each WS connection has an **asyncio task** for the LLM call, stored in `session.active_task`
- On new command while task running: cancel previous task, start new one (last-write-wins, appropriate for motion control)
- Alternative policy (queue): buffer commands in `asyncio.Queue(maxsize=1)` — drop overflow, log warning
- Default: **cancel-and-replace** (lower latency for motion control use case)

```python
async def handle_command(session, websocket, command_text, msg_id):
    if session.active_task and not session.active_task.done():
        session.active_task.cancel()
    session.active_task = asyncio.create_task(
        _run_llm_and_reply(session, websocket, command_text, msg_id)
    )
```

#### 4.3 Keepalive _(fixes: frequent WS disconnection)_
The primary cause of disconnections is proxy idle timeout (nginx default: 60 s, Cloudflare: 100 s). Fix with a two-sided heartbeat:

- **Server → Client ping**: every **20 s**, server sends `{"v":1,"type":"ping"}` via a per-connection `asyncio.Task` started on accept
- **Client → Server pong**: client replies `{"v":1,"type":"pong"}` immediately on receipt
- **Client → Server ping**: client also sends its own ping every **20 s** independently — belt-and-suspenders
- **Stale detection**: if server receives no pong within 15 s of sending a ping, it closes with code `1001` (going away); client reconnects
- **Auto-reconnect**: client uses exponential backoff — `1 s, 2 s, 4 s, 8 s, max 16 s` — not a fixed 3 s. On reconnect, attempt session resume (Spec 4.4)
- **FastAPI WebSocket keepalive**: set `ws_ping_interval=20, ws_ping_timeout=15` on the uvicorn config — this enables the ASGI-level WebSocket ping/pong as a second layer

```python
# uvicorn config in app.py
uvicorn.run("adam.app:app", host="0.0.0.0", port=8000, reload=True,
            ws_ping_interval=20, ws_ping_timeout=15)
```

```js
// client reconnect with backoff
let _reconnectDelay = 1000;
function connectWS() {
  ws = new WebSocket(...);
  ws.onopen = () => { _reconnectDelay = 1000; /* reset */ };
  ws.onclose = () => setTimeout(connectWS, _reconnectDelay = Math.min(_reconnectDelay * 2, 16000));
}
```

#### 4.4 Reconnection & State Recovery
On reconnect (client generates new WS connection):
1. Client sends `{"type": "resume", "session_id": "..."}` if it has a stored session ID (`localStorage`)
2. Server looks up session in `FileStore`, restores history
3. Server replies with `{"type": "session", "id": "...", "history": [...last 20 msgs...], "restored": true}`
4. Client replays log entries from history without re-animating

#### 4.5 Streaming Motion (future / `LLM_STREAM=true`)
When streaming is enabled:
- Server streams JSON tokens over WS as `{"type": "token", "delta": "..."}` frames
- Client accumulates delta string; attempts incremental parse to extract `keyframes` as they arrive
- As soon as ≥ 2 keyframes are available, begin animation — remaining keyframes appended mid-play
- Final `{"type": "motion", ...}` frame carries the validated complete object

#### 4.6 Error Handling & Codes
Structured error codes — never leak stack traces:

| Code | Meaning |
|---|---|
| `LLM_TIMEOUT` | LLM call exceeded timeout (`LLM_TIMEOUT_S`, default 30 s) |
| `LLM_PARSE_ERROR` | JSON parse failed after retry |
| `LLM_SCHEMA_ERROR` | Pydantic validation failed |
| `LLM_PROVIDER_ERROR` | litellm raised API error |
| `WS_DECODE_ERROR` | Client sent malformed frame |
| `SESSION_NOT_FOUND` | Resume with unknown session ID |

#### 4.7 Latency Targets

| Stage | Target |
|---|---|
| WS frame → `ack` | < 5 ms |
| `ack` → `thinking` | < 10 ms |
| `thinking` → first `token` (streaming) | < 800 ms (depends on provider) |
| `thinking` → `motion` (non-streaming) | < 3 s p50, < 6 s p95 |
| Animation start after `motion` received | < 16 ms (next render frame) |
