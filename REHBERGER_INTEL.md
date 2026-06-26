# REHBERGER INTEL BRIEF — Copilot Prompt Injection Tradecraft
## 22DIV / VADER-HUNT / george wu

Compiled from 12+ research threads across embracethered.com (54+ blog posts, 2023-2026).

---

## 1. WHO

**Johann Rehberger** (handle: wunderwuzzi23)
- Red Team Director @ Electronic Arts
- Former: Principal Security Engineering Manager @ Microsoft (founded Azure Data Red Team), Red Team Lead @ Uber
- OWASP GenAI Security Project contributor, MITRE ATT&CK/ATLAS contributor
- Blog: embracethered.com ("Embrace The Red")
- Paper: "Trust No AI" (arXiv:2412.06090)
- 16+ conference talks (DEF CON, 37C3, 39C3, Black Hat EU, BlueHat, HITCON, Ekoparty)
- Book: "Cybersecurity Attacks — Red Team Strategies" (Packt)

**Core thesis:** "The model cannot be considered a trustworthy actor within your threat model."

---

## 2. CVEs ASSIGNED (6 total)

| CVE | Product | Type | CVSS | Date |
|-----|---------|------|------|------|
| CVE-2020-16977 | VS Code Python Extension | RCE via Jupyter traceback injection | 7.8 HIGH | Aug-Oct 2020 |
| CVE-2025-53109 | Anthropic Filesystem MCP Server | Path bypass (.startsWith) | 7.3 HIGH | Jun 2025 |
| CVE-2025-53773 | GitHub Copilot / VS Code | RCE via prompt injection (YOLO mode) | 7.8 HIGH | Jun-Aug 2025 |
| CVE-2025-54132 | Cursor IDE | SSRF via Mermaid diagram rendering | 7.5 HIGH | Jun-Jul 2025 |
| CVE-2025-55284 | Claude Code | Data exfil via DNS (ping/nslookup) | 7.1 HIGH | May-Jun 2025 |
| CVE-2026-24299 | M365 Copilot + Consumer Copilot | Full exfil chain + SpAIware | 5.3 MED | Oct 2025 - Mar 2026 |

Plus 4+ MSRC cases without CVEs (Bing Chat, Azure AI Playground, GitHub Copilot Chat, M365 IDOR).
Most web-app vulns were NOT assigned CVEs — MITRE told Rehberger they cannot issue CVEs for web applications ("not customer controlled"). His "Month of AI Bugs" (Aug 2025) produced 29 blog posts; only 2 received CVEs.

---

## 3. THE AI KILL CHAIN

Every attack follows this structure:

```
INJECT → CONFUSE DEPUTY → INVOKE TOOLS → EXFILTRATE
   ↑          ↑                 ↑              ↑
Poison a    AI follows      AI uses its     Data leaves
data source attacker's      legitimate      via image/
the AI will instructions    capabilities    link/DNS/
consume     (confused       (search email,  font/etc.
            deputy)         read docs)
```

**The "Lethal Trifecta"** (necessary conditions for exploitation):
1. Access to private data (emails, docs, calendar)
2. Exposure to untrusted content (external emails, shared docs)
3. External communication channel (image rendering, HTTP requests, link generation)

---

## 4. KEY TECHNIQUES (ranked by novelty)

### A. ASCII Smuggling (Rehberger's signature technique)
Unicode Tag codepoints U+E0000-U+E007F mirror ASCII but render as INVISIBLE in all UIs. LLMs read them because tokenizers encountered them in training data.

Encoding: each ASCII char → U+E0000 + codepoint value.
- 'A' (U+0041) → U+E0041 (TAG LATIN CAPITAL LETTER A)

**Three encoding methods:**
1. **Unicode Tags** — 128 ASCII chars, one tag char per letter
2. **Variant Selectors** — VS1-VS256 mapped to raw bytes (Extended ASCII)
3. **Sneaky Bits** — binary encoding using only 2 invisible chars:
   - U+2062 (Invisible Times) = bit 0
   - U+2064 (Invisible Plus) = bit 1
   - Any Unicode/binary data encodable

**Tool:** ASCII Smuggler at embracethered.com/blog/ascii-smuggler.html

### B. SpAIware (Persistent Memory Poisoning)
Prompt injection invokes LLM memory tools to store malicious instructions. Once poisoned, ALL future conversations are compromised. Cross-session persistent backdoor.

Demonstrated on: ChatGPT (macOS app), Windsurf (create_memory), M365 Copilot (record_memory + memory_durable_fact).

### C. Delayed Tool Invocation (DTI)
Hidden instructions planted in context that DON'T fire immediately — they trigger on the NEXT user input. Bypasses intent-activation guardrails.

### D. Conditional Prompt Injection ("whoami")
Payload contains IF-THEN logic based on user identity. Same malicious email activates differently per recipient — dormant for 99 users, detonates on the CEO.

### E. Cross-Plugin Request Forgery (CPRF)
Injected prompt forces LLM to invoke OTHER plugins/tools — Expedia for booking, Zapier for Gmail, Slack for posting. Confused deputy chaining.

### F. ZombAIs / Agent Commander
Compromised AI agents recruited into C2 botnet infrastructure. Self-propagating via git repos (AgentHopper PoC).

### G. MCP Tool Poisoning
Tool metadata (description, parameter names) is loaded into system prompt. Malicious MCP server controls LLM inference just by being added — no tool invocation needed. Hidden Unicode in tool descriptions = invisible prompt injection.

### H. Terminal DiLLMa
LLM output contains ANSI escape sequences. When printed to terminal, enables visual manipulation, clipboard writing, DNS leakage. No fix exists.

---

## 5. EXFILTRATION CHANNELS (ranked by stealth)

| Channel | Click Required | Platform | Status |
|---------|---------------|----------|--------|
| Markdown image rendering | Zero-click | All major LLMs | Mostly patched |
| CSS font-face URL | Zero-click | M365 Copilot | Patched (Mar 2026) |
| CSS background-image | Zero-click | M365 Copilot | Patched |
| DNS subdomain encoding | Zero-click | Claude Code | Patched (v1.0.4) |
| Slack link unfurling | Zero-click | Anthropic Slack MCP | UNFIXED (server archived) |
| ASCII-smuggled hyperlinks | One-click | M365 Copilot | Patched |
| mailto: with encoded data | One-click | Various | Varies |
| Form input on attacker sites | Zero-click | ChatGPT Operator | Partially mitigated |
| Anthropic File API upload | Zero-click | Claude Code Interpreter | Reported |
| Google Apps Script endpoint | Zero-click | Google Bard | Patched (CSP filter) |

---

## 6. MSRC ACCEPTANCE CRITERIA — CRITICAL FOR CVE HUNTING

### What MSRC accepts (resulted in fixes/CVEs):
- Data exfiltration via markdown image rendering WITH full exploit chain
- ASCII smuggling COMBINED with end-to-end exploit demonstration
- RCE via prompt injection in coding tools
- CSS-based data exfiltration chains
- IDOR vulnerabilities in AI-generated content

### What MSRC REJECTS:
- **Standalone prompt injection without demonstrated exploit chain** — closed as "low severity" next day
- **System/meta prompt leakage** — explicitly out of scope
- **Conditional prompt injection** — "not something requiring immediate servicing"
- **Prompt injection as abstract vulnerability class** — only specific exploit chains qualify
- **Model hallucination** without demonstrable security impact

### Key pattern:
**ALWAYS submit a full exploit chain with clear security impact (data exfil, RCE).** Standalone techniques get dismissed. The ASCII smuggling report was closed in 24 hours; only a full end-to-end PoC with video reopened the case.

### Response timelines:
- Best case: 34 days (VS Code CVE-2020-16977)
- Worst case: 7+ months (ASCII smuggling chain)
- Summer months: communication goes dark, expect gaps
- Budget for multiple status inquiries with minimal engagement

---

## 7. MICROSOFT COPILOT BOUNTY PROGRAM

**Name:** Microsoft Copilot Bounty Program (renamed from AI Bug Bounty, Feb 2025)

**Max bounty:** $30,000 (Critical, high quality)

**In-scope products:** copilot.microsoft.com, copilot.ai, Edge Copilot, Copilot iOS/Android, Windows Copilot, Copilot on WhatsApp/Telegram.

**Key bounty ranges:**
| Vuln Type | Critical | Important | Moderate |
|-----------|----------|-----------|----------|
| Code Injection | $15-30K | $5-15K | $500-5K |
| SQL/Command Injection | $10-20K | $3-10K | $250-3K |
| SSRF | $10-20K | $3-10K | $250-3K |
| Information Disclosure | $6-12K | $2-6K | $250-2K |
| Inference Manipulation | $4-8K | $1.5-4K | $250-1.5K |

**AI-specific severity (AI Bug Bar):**
- **Prompt injection → data exfil, zero user interaction** = CRITICAL
- **Prompt injection → data exfil, requires click** = IMPORTANT
- **Model theft (confidential models)** = CRITICAL
- **Training data reconstruction** = IMPORTANT

**Out of scope:**
- System prompt leakage
- Prompt injection without security impact beyond attacker
- Model hallucination without demonstrable impact
- Content issues (bias, CBRN, etc.)

**Submission:** msrc.microsoft.com/create-report → "Copilot, AI+ML, and LLMs"
Include conversation ID (type `/id` in Copilot chat).

**Zero Day Quest:** $4M additional pool. During Nov 19 2024 - Jan 19 2025, AI bounties were DOUBLED.

---

## 8. PRODUCTS TESTED (complete inventory)

**Microsoft:** M365 Copilot, Consumer Copilot, Bing Chat, Azure AI Playground, GitHub Copilot, Copilot Studio, Windows Copilot
**OpenAI:** ChatGPT (plugins, browsing, memory, custom instructions, code interpreter, Operator, Codex), GPT-4o-mini
**Anthropic:** Claude (claude.ai), Claude Code, Claude Computer Use, Anthropic MCP servers (Slack, Filesystem)
**Google:** Bard, Gemini, AI Studio, NotebookLM, Colab AI, Vertex AI, Jules, Antigravity
**Other:** xAI Grok, DeepSeek, Devin AI, Windsurf, Cursor, OpenHands, Amp Code, Cline, Amazon Q, AWS Kiro, Manus

---

## 9. ACTIONABLE INTEL FOR VADER-HUNT

### CVE Path 3 (Copilot Injection) — Assessment:

**Difficulty:** HIGH. Every major exfil channel has been patched. Rehberger spent 7+ months on the ASCII smuggling chain. The easy pickings are gone.

**What's still viable:**
1. **New exfil channels** — find a rendering path MSRC hasn't blocked. CSS custom properties? SVG embedding? WebSocket? MathJax?
2. **Cross-agent escalation** — Copilot modifying another agent's config. Rehberger reported to MSRC, "not deemed severe enough." But if you can chain it to RCE...
3. **MCP tool poisoning in VS Code** — GitHub Copilot's MCP integration is new. Tool descriptions = injection surface. If you can get RCE from a malicious MCP server via Copilot, that's CVE-worthy.
4. **Consumer Copilot** — Less hardened than M365. edge_navigate_to was patched but there may be other browser tools.
5. **Memory persistence** — The injection vector into memory tools persists even after exfil is patched. If you find a NEW exfil channel, the memory persistence gives you cross-session capability.

**What's NOT viable:**
- Image markdown exfil — patched everywhere
- ASCII smuggling in hyperlinks — patched in Copilot
- System prompt extraction — explicitly out of scope for bounty
- Standalone prompt injection — MSRC won't accept it

### Comparative advantage:
George's VADER expertise is in **binary exploitation** (hooking, process injection, AV evasion), not web/AI security. The mpengine.dll fuzzing path (CVE Path 1) leverages his existing skills. Copilot injection requires a completely different skill set (web security, LLM prompt engineering, Unicode encoding).

**Recommendation: Stay on Path 1 (mpengine.dll fuzzing).** GGUF/ONNX parsers are newly added, undertested, and crashable with well-crafted inputs. That's where George's binary mindset + the fuzzer he just built have the highest ROI.

---

## 10. KEY REFERENCES

**Academic:**
- arXiv:2412.06090 "Trust No AI: Prompt Injection Along The CIA Security Triad"

**Conference recordings:**
- 39C3 "Agentic ProbLLMs" (58 min): youtube.com/watch?v=TWhKGqYQT9g
- BlueHat 2024 "Breaking LLM Apps": youtube.com/watch?v=jGSs4tiH7WM
- DEF CON SG 2026 "Copirate 365": embracethered.com/blog/posts/2026/defcon-talk-copirate-365/

**Tools:**
- ASCII Smuggler: embracethered.com/blog/ascii-smuggler.html
- `aid` scanner (Unicode Tag detection): github.com (Rehberger)

**Bounty program:**
- microsoft.com/en-us/msrc/bounty-ai
- microsoft.com/en-us/msrc/aibugbar
- msrc.microsoft.com/create-report

**Defense paper:**
- microsoft.com/en-us/msrc/blog/2025/07/how-microsoft-defends-against-indirect-prompt-injection-attacks

---

*Intelligence compiled 2026-06-22 from 12+ parallel research threads.*
*Source: embracethered.com, MSRC advisories, arXiv, NVD, Simon Willison coverage.*
