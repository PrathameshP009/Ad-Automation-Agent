# CrowdWisdomTrading — AI Video Ads Agent Team

A **Hermes** (`hermes-ai`) multi-agent pipeline that researches winning trading-niche ads,
turns them into a cinematic 30–60s video ad script, and renders the ad — for
[crowdwisdomtrading.com](https://crowdwisdomtrading.com).

```
Ads Manager Agent  →  Script Agent  →  Video Agent
  (Apify: Meta Ad      (Tavily/Exa:      (OpenMontage /
   Library scraping     ICP + pain        ffmpeg render
   + concept mining)     point research)   pipeline)
```

## Why this design

The brief explicitly says: **no text ads, make it cinematic, make it "wow."** So the
pipeline is built around one idea: the Script Agent doesn't just write ad copy — it writes
a **shot-by-shot cinematic storyboard** (camera direction, VO, on-screen data overlays,
music cues) that the Video Agent can mechanically turn into a montage. The "wow" comes from
combining real market pain points (mined from research, not made up) with a hard visual hook
in the first 2 seconds — the classic "pattern interrupt" that stops the scroll.

## Architecture

```
crowdwisdom-video-ads/
├── agents/
│   ├── ads_manager_agent.py   # Agent 1: sources & analyzes winning ads
│   ├── script_agent.py        # Agent 2: research + storyboard writer (x3 script types)
│   └── video_agent.py         # Agent 3: storyboard -> rendered .mp4
├── tools/
│   ├── apify_tool.py          # Meta Ad Library scraping via Apify
│   ├── tavily_tool.py         # Tavily search (ICP / pain-point research)
│   ├── exa_tool.py            # Exa neural search (alternative/second source)
│   └── video_gen_tool.py      # OpenMontage adapter + ffmpeg fallback renderer
├── orchestrator.py            # Hermes multi-agent kanban orchestration
├── config.py                  # env/config loading
├── main.py                    # CLI entrypoint
├── requirements.txt
├── .env.example
└── outputs/                   # ads.json, script_*.json, final ad .mp4 land here
```

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
```

Required keys (all have free tiers):

| Key | Used for | Get it at |
|---|---|---|
| `OPENROUTER_API_KEY` | LLM calls (all 3 agents) | https://openrouter.ai/keys |
| `APIFY_API_TOKEN` | Meta Ad Library scraping | https://console.apify.com/account/integrations |
| `TAVILY_API_KEY` | ICP/pain-point search | https://app.tavily.com |
| `EXA_API_KEY` | secondary neural search | https://exa.ai |

By default the LLM model is `openrouter/free`, which lets OpenRouter select an available free
model for both fast and creative steps. Set `LLM_MODEL_FAST` and `LLM_MODEL_CREATIVE` to any
currently available OpenRouter model IDs when you want to pin a model — both are swappable in
`config.py`. NVIDIA `build.nvidia.com` endpoints work too (OpenAI-compatible base_url).

## Running it

```bash
python main.py --product "algorithmic trading signals" --niche "retail day traders"
```

This runs the full pipeline and writes to `outputs/`:
- `outputs/ads.json` — top performing ads (last 30 days) + extracted pain/marketing concepts
- `outputs/script_<type>.json` — 3 storyboards (see Script Agent below)
- `outputs/final_ad.mp4` — rendered cinematic ad for the best-scoring script

Run a single stage for debugging:
```bash
python main.py --stage ads
python main.py --stage script --pain-input outputs/ads.json
python main.py --stage video --script outputs/script_1.json
```

## Agent 1 — Ads Manager Agent

1. `tools/apify_tool.py` calls an Apify Meta Ad Library actor (e.g.
   `jupri/facebook-ads-scraper` or `curious_coder/facebook-ads-library-scraper` — both
   free-tier actors on the Apify Store) filtered to trading/fintech advertisers, last 30 days,
   video format.
2. Results are scored by a heuristic (days active, "impressions bucket" if available,
   creative variety count — Meta Ad Library exposes days-running as a strong proxy for
   "this ad is working," since advertisers kill losing ads fast) and the top N are kept.
3. A second LLM pass (`extract_concepts()` in `ads_manager_agent.py`) reads each ad's
   copy/transcript and extracts: **pain point**, **marketing angle/hook**, **CTA style**,
   **visual pattern** (talking head / data overlay / UGC / cinematic).
4. Saved to `outputs/ads.json`.

## Agent 2 — Script Agent

For **each of the 3 angles** derived from step 1's top pain points, the agent:

1. Searches Tavily (`tavily_tool.py`, `time_range="month"`) and Exa (`exa_tool.py`) for
   recent discussion of that pain point + ICP (e.g. "retail day traders overtrading losses
   2026", "why retail traders lose money algo signals").
2. Pulls CrowdWisdomTrading's differentiators from `prompts/unique_data.md` (fill this in
   with the "unique data" examples referenced in the brief — proprietary sentiment/options-flow
   data, analyst call transcripts, etc. — since those source links weren't accessible from the
   PDF, this is a stub for you to complete with the actual CWT data assets).
3. Writes a **cinematic storyboard** as structured JSON: hook (0-3s), problem (3-15s),
   turn/solution (15-40s), proof/data-flash, CTA — each shot has `visual`, `vo_line`,
   `on_screen_text`, `sfx_music_cue`, `duration_sec`.
4. Saves human-readable JSON to `outputs/script_<n>.json`.

## Agent 3 — Video Agent

`tools/video_gen_tool.py` takes a storyboard JSON and renders it two possible ways:

- **Default: ffmpeg pipeline** (`render_with_ffmpeg_fallback()`) — sources imagery relevant
  to each shot, Ken-Burns pans each still, burns in `on_screen_text` (or the voiceover line
  when no separate caption is provided), and synthesizes each `vo_line` locally with
  the natural English male neural voice `en-US-GuyNeural` by default (override with
  `TTS_VOICE`). Each complete shot narration is synthesized as one take to preserve natural
  speech rhythm. Word-boundary timing drives the captions, which update during the continuous
  narration; a 0.5-second pause follows each comma, dash, or sentence-ending punctuation mark.
  A supplied `music_bed_path` is mixed quietly beneath the narration. Install dependencies with
  `pip install -r requirements.txt`; neural speech generation requires an internet connection.
  The final audio is loudness-normalized. This produces a narrated, captioned
  `.mp4` without a paid TTS service. Storyboards may specify a `scene_type` to render a
  consistent, legible, shot-specific trading graphic rather than rely on unrelated AI
  portraits or illegible generated screen text.
- **Experimental: OpenMontage** — `render_with_openmontage()` remains an adapter stub.
  Enable it explicitly only after confirming that the installed OpenMontage version produces
  narration and audio in its rendered output.

## Hermes orchestration + kanban

`orchestrator.py` registers all three agents on a `hermes.core.Team` / kanban board so the
3-stage pipeline is visible as moving cards (`To Research → Scripting → Rendering → Done`).
Run:

```bash
python orchestrator.py --ui
```
and screen-record that board moving through the 3 stages for the submission video.

## Submission checklist (per the brief)

- [ ] GitHub/GitLab repo link
- [ ] Apify + Tavily (+ Exa) tokens included in a **separate, non-committed** `keys_for_reviewer.txt`
      (do NOT commit real keys to git — see note below) so Gilad can rerun without burning
      his own accounts
- [ ] Screen recording of the Hermes kanban board running the pipeline
- [ ] Email to gilad@crowdwisdomtrading.com with repo link + video + keys

> **Security note:** never commit live API keys to a public repo. Put them in a `.env` that's
> `.gitignore`'d, and send the reviewer keys directly in the email body or an encrypted note —
> not in git history.

## What's genuinely a stub vs. what's real

To be transparent about where you'll need to do real work before submitting:
- **Real, runnable**: agent structure, Apify/Tavily/Exa API calls, LLM prompt chains, JSON
  schemas, ffmpeg fallback renderer, CLI.
- **You need to fill in**: `prompts/unique_data.md` with CWT's actual proprietary data
  assets (the brief references specific links that didn't resolve for me), the exact Apify
  actor ID you have access to (Meta Ad Library actors change/get deprecated — check the Apify
  Store for current ones), and OpenMontage's actual CLI flags once you clone it (I've stubbed
  the adapter with the interface but haven't run against the live repo).
- **Creative judgment call**: the actual hook/visual ideas in the sample script are AI-written
  starting points — the "wow" factor Gilad is evaluating should reflect your own creative edit
  pass on top of what the agent generates, not the raw output.
