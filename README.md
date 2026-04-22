# ADAM — Robot Brain Interface

A web app where an LLM acts as the motor cortex of a humanoid 3D robot.
You speak/type natural language → the LLM generates bone rotation keyframes → the 3D model moves.

Uses [litellm](https://github.com/BerriAI/litellm) so you can swap between providers (Gemini, Groq, Anthropic, OpenAI, etc.) by changing your `.env`.

## Project Structure

```
adam/
├── pyproject.toml           # uv project — deps, scripts, build
├── .env                     # LLM provider/model/key (git-ignored)
├── .env.example
├── static/
│   └── index.html           # Three.js frontend (served by FastAPI)
└── src/
    └── adam/
        ├── __init__.py
        ├── app.py           # FastAPI app, static mount, logging setup
        ├── config.py        # LLMConfig dataclass, loads .env
        ├── skeleton.py      # Bone map + LLM system prompt
        ├── routes.py        # REST + WebSocket endpoints (litellm)
        ├── state.py         # AppState + Session dataclasses
        └── history.py       # Session CRUD + message persistence
```

## Setup

```bash
# 1. Install uv (if you haven't already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Copy and fill in .env
cp .env.example .env
# Edit .env — set LLM_PROVIDER, LLM_MODEL, LLM_API_KEY

# 3. Install dependencies & run
uv run adam
```

Then open http://localhost:8000

## Configuration

All settings live in `.env`:

| Variable        | Description                              | Example                      |
|-----------------|------------------------------------------|------------------------------|
| `LLM_PROVIDER`  | litellm provider name                   | `gemini`, `groq`, `anthropic`|
| `LLM_MODEL`     | Model identifier (litellm format)       | `gemini/gemini-2.0-flash`    |
| `LLM_API_KEY`   | API key for the provider                | `AIza...`                    |
| `LLM_BASE_URL`  | Optional custom base URL                |                              |
| `LLM_STREAM`    | Enable streaming (not yet used)         | `true`                       |
| `LLM_MAX_TOKENS` | Max completion tokens requested from model | `768`                     |
| `HISTORY_MAX_TOKENS` | Token budget for chat history only (recency window) | `1200`             |
| `HISTORY_MAX_MESSAGES` | Max recent messages kept in LLM context | `8`                       |
| `HISTORY_MESSAGE_MAX_CHARS` | Per-message truncation before sending to LLM | `180`            |
| `MOTION_CACHE` | Enable LRU cache for repeated commands | `true`                         |
| `MOTION_CACHE_SIZE` | Number of cached motions                | `50`                        |

Tip: for Groq on-demand tiers, lower `LLM_MAX_TOKENS` and keep history compact (`HISTORY_MAX_MESSAGES`, `HISTORY_MESSAGE_MAX_CHARS`) to avoid request-too-large errors.

## How it works

1. You type a command ("wave your right hand", "jump", "bend down and touch the floor")
2. The command goes over WebSocket to the FastAPI backend
3. Backend calls the configured LLM (via litellm) with a system prompt containing the full skeleton bone map
4. The LLM returns a JSON motion plan — an array of keyframes with bone rotations (in degrees)
5. The frontend interpolates between keyframes and applies rotations to the procedural 3D humanoid
6. Conversation history is persisted per session so the LLM has context for follow-up commands

## API Endpoints

| Endpoint         | Method    | Description                          |
|------------------|-----------|--------------------------------------|
| `/`              | GET       | Serves index.html                    |
| `/api/command`   | POST      | Single REST command → motion JSON    |
| `/ws`            | WebSocket | Real-time duplex command channel     |

### REST example

```bash
curl -X POST http://localhost:8000/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "raise both arms above your head"}'
```

### Motion JSON schema (what the LLM returns)

```json
{
  "description": "raising both arms overhead",
  "keyframes": [
    {
      "time": 0.0,
      "bones": [
        { "name": "LeftArm",  "rotation": { "z": 0 } },
        { "name": "RightArm", "rotation": { "z": 0 } }
      ]
    },
    {
      "time": 0.6,
      "bones": [
        { "name": "LeftArm",  "rotation": { "z": 160 } },
        { "name": "RightArm", "rotation": { "z": -160 } }
      ]
    }
  ],
  "loop": false,
  "totalDuration": 0.6
}
```

## Extending

- **Add a real GLTF model**: Replace the procedural mesh with `THREE.GLTFLoader` + a Mixamo export. The bone names in the system prompt already match the Mixamo rig convention.
- **Add speech input**: Wire the Web Speech API to the input box for voice commands.
- **Multi-step motions**: Ask for sequences like "walk forward then stop and wave" — the LLM will chain keyframes.
- **Switch providers**: Change `LLM_PROVIDER` and `LLM_MODEL` in `.env` to use any litellm-supported provider.