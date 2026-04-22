# ADAM — Robot Brain Interface

A web app where an LLM acts as the motor cortex of a humanoid 3D robot.
You speak/type natural language → the LLM generates one or more human-like animation plans → the 3D model moves.

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
| `MOTION_CACHE_SIZE` | Number of cached animation responses    | `50`                        |

Tip: for Groq on-demand tiers, lower `LLM_MAX_TOKENS` and keep history compact (`HISTORY_MAX_MESSAGES`, `HISTORY_MESSAGE_MAX_CHARS`) to avoid request-too-large errors.

## How it works

1. You type a command ("wave your right hand", "jump", "bend down and touch the floor", "step left then bow")
2. The command goes over WebSocket to the FastAPI backend
3. Backend calls the configured LLM (via litellm) with a system prompt containing the full skeleton bone map
4. The LLM returns a JSON animation response containing one or more motion plans, each with ordered keyframes and bone rotations (in degrees)
5. The frontend plays the returned animations in sequence and applies rotations to the procedural 3D humanoid
6. Conversation history is persisted per session so the LLM has context for follow-up commands

## API Endpoints

| Endpoint         | Method    | Description                          |
|------------------|-----------|--------------------------------------|
| `/`              | GET       | Serves index.html                    |
| `/api/sessions`  | GET       | Lists known in-memory session ids    |
| `/api/sessions/{session_id}` | DELETE | Deletes a stored session     |
| `/api/sessions/{session_id}/reset` | POST | Clears a stored session |
| `/ws`            | WebSocket | Real-time duplex command channel     |

### WebSocket response schema

The server sends motion frames shaped like this:

```json
{
  "v": 1,
  "type": "motion",
  "ref": "message-id",
  "animations": [
    {
      "description": "step left",
      "keyframes": [
        {
          "time": 0.0,
          "grounded": true,
          "bones": [
            { "name": "Hips", "rotation": { "z": 0 } }
          ]
        },
        {
          "time": 0.7,
          "grounded": true,
          "bones": [
            { "name": "Hips", "rotation": { "z": 8 } },
            { "name": "LeftUpLeg", "rotation": { "x": -18, "z": 12 } }
          ]
        }
      ],
      "loop": false,
      "totalDuration": 0.7
    },
    {
      "description": "bow",
      "keyframes": [
        {
          "time": 0.0,
          "grounded": true,
          "bones": []
        },
        {
          "time": 0.8,
          "grounded": true,
          "bones": [
            { "name": "Spine", "rotation": { "x": 22 } },
            { "name": "Spine1", "rotation": { "x": 18 } },
            { "name": "Spine2", "rotation": { "x": 12 } }
          ]
        }
      ],
      "loop": false,
      "totalDuration": 0.8
    }
  ],
  "motion": {
    "description": "step left",
    "keyframes": [
      {
        "time": 0.0,
        "grounded": true,
        "bones": [
          { "name": "Hips", "rotation": { "z": 0 } }
        ]
      },
      {
        "time": 0.7,
        "grounded": true,
        "bones": [
          { "name": "Hips", "rotation": { "z": 8 } },
          { "name": "LeftUpLeg", "rotation": { "x": -18, "z": 12 } }
        ]
      }
    ],
    "loop": false,
    "totalDuration": 0.7
  }
}
```

`motion` is kept as a compatibility alias for the first animation. New clients should read `animations`.

## Extending

- **Add a real GLTF model**: Replace the procedural mesh with `THREE.GLTFLoader` + a Mixamo export. The bone names in the system prompt already match the Mixamo rig convention.
- **Add speech input**: Wire the Web Speech API to the input box for voice commands.
- **Multi-step motions**: Ask for sequences like "walk forward then stop and wave" — the LLM can now return multiple ordered animations for one command.
- **Human movement**: The prompt treats ADAM as a full-body humanoid, so whole-body actions like stepping, crouching, turning, balancing, and jumping are expected when the rig supports them.
- **Switch providers**: Change `LLM_PROVIDER` and `LLM_MODEL` in `.env` to use any litellm-supported provider.