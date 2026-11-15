# Torque Spec

![CI](https://github.com/mstrdave/torquespec/actions/workflows/ci.yml/badge.svg)

A diagnosis assistant and spec reference for one car: the **1990 Mazda MX5 Miata** (NA6, 1.6 L B6ZE). Describe what the car is doing and Claude works through it the way a good mechanic would: it asks the questions that matter, ranks the likely causes for this specific engine, gives a cheap test for each one before you buy parts, and walks you through the fix with the right torque values.

The specs, flash codes and known problems for this car live in versioned JSON files, so the model answers from real reference data instead of guessing, and the same data powers searchable tables that work with no API key at all.

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...   # only needed for the Diagnose tab
torquespec                     # http://127.0.0.1:8000  (API docs at /docs)
pytest
```

## What it does

| Tab | What you get |
|---|---|
| **Diagnose** | Streaming chat with Claude. The latest message is matched against known issues for this model and the matches are passed along as hints. |
| **Torque specs** | 22 fasteners with ft-lb or in-lb ranges, N·m conversions and notes. Search matches every word you type. |
| **Flash codes** | How to read codes on a pre-OBD-II car (jumper TEN to GND, count the check engine light flashes) and what each code means. |
| **Known issues** | The NA6's usual suspects: short-nose crank wobble, CAS O-ring leaks, hunting idle, clogged top drains and more, each with symptoms, cause and fix. |

## How the LLM part is built

- **Grounded prompt.** `knowledge.render_reference()` turns the JSON data into a deterministic text block that goes in the system prompt with the diagnostic instructions. Values that are less certain are tagged `[verify]`, and the model is told to say so and point to the workshop manual.
- **Prompt caching.** The system prompt is byte-for-byte stable across requests and marked with `cache_control`, so every turn after the first reads the reference data from cache.
- **Streaming.** `/api/diagnose` streams Server-Sent Events from `AsyncAnthropic.beta.messages.stream`; the browser renders tokens as they arrive.
- **Model settings.** `claude-opus-5-5` with adaptive thinking at `high` effort. Server-side fallbacks (`fallbacks="default"`) are on, so if a safety classifier declines a request the API retries it on a fallback model in the same call. `refusal` and `max_tokens` stop reasons are reported to the user instead of failing silently.
- **Safety rules in the prompt.** The model must say when the car should not be driven (brakes, steering, fuel leaks, overheating) and remind the owner to use jack stands.
- **Input validation.** Conversations must alternate user/assistant turns, start and end with the user, and stay within size limits (Pydantic, 422 on bad input). With no API key the app returns 503 for diagnosis and keeps serving everything else.

## Layout

```
src/torquespec/
  data/           vehicle.json, torque_specs.json, trouble_codes.json, known_issues.json
  knowledge.py    loading, search, unit conversion, prompt rendering, symptom matching
  diagnose.py     prompt construction and streaming from Claude
  app.py          FastAPI routes and SSE endpoint
  static/         single-page UI (vanilla JS, light and dark themes)
tests/            knowledge and API tests (the LLM is replaced by a fake in tests)
```

## About the data

The values come from commonly published figures for the 1990 to 1993 1.6 L cars. Entries tagged **verify** are ones where sources disagree or where I could not confirm the exact number. **Always check critical values against the factory workshop manual** before you torque a head bolt or a brake caliper. Corrections are welcome: edit the JSON and open a pull request.

## License

MIT
