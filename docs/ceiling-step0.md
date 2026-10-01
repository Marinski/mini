# ContextMode offline ceiling (step 0)

Share of tool-output bytes in outputs over 5,000 bytes - what ContextMode would index.

| Source | Task | Tool calls | Tool output | Indexed-able | Share |
|---|---|---|---|---|---|
| batch9-gate / opencode-t7-1.jsonl | t7 | 15 | 0.05 MB | 0.04 MB | **80.6%** |
| batch9-gate / opencode-t8-1.jsonl | t8 | 36 | 0.09 MB | 0.06 MB | **72.7%** |
| batch9-gate / opencode-t9-1.jsonl | t9 | 101 | 0.10 MB | 0.04 MB | **40.4%** |
| batch9 / opencode-t7-1.jsonl | t7 | 41 | 0.09 MB | 0.07 MB | **74.9%** |
| batch9 / opencode-t7-2.jsonl | t7 | 38 | 0.08 MB | 0.06 MB | **73.9%** |
| batch9 / opencode-t8-1.jsonl | t8 | 85 | 0.15 MB | 0.09 MB | **62.2%** |
| batch9 / opencode-t8-2.jsonl | t8 | 73 | 0.10 MB | 0.05 MB | **45.6%** |
| batch9 / opencode-t9-1.jsonl | t9 | 79 | 0.07 MB | 0.03 MB | **43.6%** |
| batch9 / opencode-t9-2.jsonl | t9 | 80 | 0.07 MB | 0.03 MB | **35.0%** |
| ats-calc integration gap analysis | - | 203 | 0.22 MB | 0.07 MB | **30.8%** |
| Git pull missing feat/suite-v1-library ref | - | 122 | 0.48 MB | 0.38 MB | **79.5%** |
| Implementing ats-imagekit spec | - | 102 | 0.15 MB | 0.10 MB | **70.8%** |
| Implement skill handoff state verification | - | 1325 | 1.95 MB | 0.96 MB | **49.3%** |
| Mini harness test next batch session | - | 300 | 0.34 MB | 0.11 MB | **32.8%** |
| Implement QDM warehouse handoff features | - | 1309 | 2.13 MB | 1.10 MB | **51.7%** |
| Backtester equity reconstruction data type | - | 1372 | 2.72 MB | 1.49 MB | **54.8%** |
| Resume task after handoff review | - | 1496 | 1.94 MB | 0.83 MB | **42.9%** |
| Codebase review and spec improvements | - | 1132 | 1.59 MB | 0.77 MB | **48.6%** |
| Sai codebase features for MCP agent | - | 393 | 0.78 MB | 0.47 MB | **59.9%** |

| **Trial transcripts pooled** | - | 548 | 0.80 MB | 0.46 MB | **57.9%** |
| **Trial transcripts median per session** | - | - | - | - | **62.2%** |

| **Real host sessions pooled** | - | 7754 | 12.30 MB | 6.29 MB | **51.1%** |
| **Real host sessions median per session** | - | - | - | - | **50.5%** |

| **Trial t7 only pooled** | - | 94 | 0.21 MB | 0.16 MB | **75.8%** |
| **Trial t7 only median per session** | - | - | - | - | **74.9%** |

| **Trial t8 only pooled** | - | 194 | 0.34 MB | 0.21 MB | **59.8%** |
| **Trial t8 only median per session** | - | - | - | - | **62.2%** |

| **Trial t9 only pooled** | - | 260 | 0.24 MB | 0.10 MB | **39.7%** |
| **Trial t9 only median per session** | - | - | - | - | **40.4%** |

## Which tools produce the indexable bytes (real host sessions)

| Tool | Bytes | Share |
|---|---|---|
| bash | 5.93 MB | 48.2% |
| read | 5.50 MB | 44.7% |
| grep | 0.23 MB | 1.9% |
| task | 0.18 MB | 1.4% |
| todowrite | 0.15 MB | 1.2% |
| websearch | 0.12 MB | 1.0% |
| skill | 0.09 MB | 0.7% |
| edit | 0.03 MB | 0.2% |
