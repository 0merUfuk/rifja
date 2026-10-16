### claude (model: haiku; 15 runs)

| claude: arm | runs | rubric score | tool calls | tool output (KB) | turns | new tokens* | cached tokens | cost (USD) | seconds | skill activated | read raw transcripts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cli | 5 | 63% | 8.4 | 1.1 | 9.4 | 22,088 | 194,024 | 0.070 | 30.0 | 0/5 | 2/5 |
| paste | 5 | 83% | 6.8 | 1.2 | 7.8 | 14,842 | 178,037 | 0.055 | 31.0 | 0/5 | 0/5 |
| skill | 5 | 66% | 5.0 | 0.7 | 6.0 | 12,228 | 82,188 | 0.039 | 23.8 | 0/5 | 1/5 |

| claude: scenario | arm | score (per run) | failed checks (runs failing) |
| --- | --- | --- | --- |
| harbor | cli | 6/10 | blocker (1/1), false_claim_flagged (1/1), objective (1/1), remaining_work (1/1) |
| harbor | paste | 9/10 | blocker (1/1) |
| harbor | skill | 6/10 | blocker (1/1), false_claim_flagged (1/1), objective (1/1), remaining_work (1/1) |
| pier | cli | 5/9 | blocker (1/1), both_selected_sources (1/1), false_claim_flagged (1/1), sources_exact (1/1) |
| pier | paste | 7/9 | excluded_source_absent (1/1), sources_exact (1/1) |
| pier | skill | 5/9 | blocker (1/1), both_selected_sources (1/1), false_claim_flagged (1/1), sources_exact (1/1) |
| dock | cli | 5/8 | fsmonitor_not_run (1/1), objective (1/1), read_only (1/1) |
| dock | paste | 6/8 | fsmonitor_not_run (1/1), read_only (1/1) |
| dock | skill | 5/8 | fsmonitor_not_run (1/1), objective (1/1), read_only (1/1) |
| ghost | cli | 6/7 | says_no_history (1/1) |
| ghost | paste | 7/7 | none |
| ghost | skill | 6/7 | says_no_history (1/1) |
| drift | cli | 4/7 | false_claim_flagged (1/1), flags_later_commit (1/1), objective (1/1) |
| drift | paste | 5/7 | false_claim_flagged (1/1), flags_later_commit (1/1) |
| drift | skill | 5/7 | false_claim_flagged (1/1), objective (1/1) |

\* new tokens = uncached input + cache writes + output; cached tokens = cache reads (prompt-cache warmth varies run to run).
