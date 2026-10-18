<!-- last-consolidated: 2026-10-18T04:56:12+00:00 -->
# MEMORY.md

## Project
- student_id_last4: 4833 (2026-09-27)
- git_branch: hw6-work (2026-09-24)
- port: 8333 (2026-09-02)
- database_name: s4833_doc (2026-09-21)
- domain: Clinical Trial Listings (2026-09-26)
- local_model: qwen3:8b (2026-09-05)
- canvas_filename: Kulshrestha_HW6.pdf (2026-09-23)
- seed: 4833 (2026-09-01)
- embedding_model: nomic-embed-text (2026-09-15)
- verify_seed: 264833 (2026-09-01)
- port_base_formula: 8000 + (SID4 mod 900) (2026-09-02)
- repo_name: data260-4833 (2026-09-01)
- report_path: reports/hw06/report.pdf (2026-09-04)
- collection_trials: clinical_trials (2026-09-04)
- route_prefix: /api/hw6/trials (2026-09-25)
- mongo_runtime: local Docker container hw6_mongo (2026-10-01)
- hardware: MacBook Pro (2026-09-01)
- model_runtime: Ollama on localhost:11434 (2026-09-01)

## Preferences
- test_command: pytest -q test_hw6_offline.py (2026-10-02)
- max_reply_tokens: 400 (2026-10-01)
- final_tag: hw6 (2026-09-04)
- chat_endpoint: /api/chat (2026-09-05)
- memory_endpoint: /api/memory/{user_id} (2026-09-06)
- aggregate_endpoint: /api/aggregate/{user_id} (2026-09-07)
- compression_policy: compress_older (2026-10-03)
- probe_count: 5 (2026-09-09)
- summary_every: 5 user messages (2026-09-10)
- experiment_users: exp_n4, exp_n12, exp_n30, exp_compress (2026-10-17)

## Resolved contradictions
- port: kept "8333" (2026-09-02); replaced "8000" (2026-09-20) - recency rule picked "8000" but AGENT.md says "8333", so it was corrected
- local_model: kept "qwen3:8b" (2026-09-05); replaced "qwen3:1.7b" (2026-09-18) - recency rule picked "qwen3:1.7b" but AGENT.md says "qwen3:8b", so it was corrected
- embedding_model: kept "nomic-embed-text" (2026-09-15); replaced "all-minilm" (2026-09-06) - most recent value wins
- max_reply_tokens: kept "400" (2026-10-01); replaced "200" (2026-09-03) - most recent value wins
