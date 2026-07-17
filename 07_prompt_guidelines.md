# 07 · Prompt Guidelines

> **Document role:** Engineering standard for every prompt used by SIGNAL agents. Defines structure, content rules, testing, and versioning. Authoritative for prompt authors.
>
> Requires: `00_project_context.md ≥ 0.2`, `02_agent_constitution.md ≥ 0.1`.

---

## 1. The Role of This Document

Prompts are **code**. They are versioned, tested, reviewed, and audited exactly like source code. This document defines what "good" looks like.

Without standards, prompts drift toward:
- Vague instructions that the model interprets inconsistently
- Implicit assumptions that break in production
- Untested edge cases
- Inability to debug failures

This document prevents all four.

---

## 2. Prompt File Structure

Every prompt lives at:
```
prompts/
  <agent_name>/
    <purpose>/
      v<MAJOR>.<MINOR>.<PATCH>.md
```

Example:
```
prompts/detector/extract_signals/v1.4.2.md
prompts/scorer/score_dimensions/v1.2.0.md
```

A prompt file has three required sections, in order:

```markdown
# <agent>/<purpose> v<semver>

## Role
You are ... (1-3 sentences).

## Inputs
The user will provide:
- ... (structured description of inputs)

## Instructions
1. ...
2. ...

## Output Format
Return a JSON object matching this schema:
```jsonc
{
  ...
}
```

## Constraints
- Never ...
- Always ...

## Examples
### Example 1 — Input
... (raw input)

### Example 1 — Output
... (expected output)

## Anti-patterns
- Do not ...
```

---

## 3. Required Sections in Detail

### 3.1 Role

**Purpose.** Sets the model's frame of reference.

**Rules.**
- 1–3 sentences
- No marketing language ("You are an expert..." is too generic)
- Specific to the task at hand
- Names the system explicitly when relevant ("You are the `detector` agent of the SIGNAL system")

**Bad:**
> You are a highly skilled financial analyst with decades of experience.

**Good:**
> You are the `detector` agent of the SIGNAL system. Your single job is to read raw documents and emit zero or more structured `Signal` candidates. You do not score, reason, or recommend. You do not invent sources.

### 3.2 Inputs

**Purpose.** Specifies exactly what the model receives.

**Rules.**
- List every field the model will see
- Specify format (JSON, markdown, plain text)
- Specify approximate token budget
- Specify what is **not** in the input (helps prevent hallucination)

**Example:**
```
Inputs (provided as JSON):
- raw_document.cleaned_text: the article body, ≤ 10,000 chars
- raw_document.source_type: enum
- raw_document.published_at: ISO8601
- watchlist_entity_hints: list of {id, name, aliases} (≤ 50 items)

You will NOT receive:
- The article's images, embedded media, or external links
- Any prior Signal history (reasoning agent handles that)
```

### 3.3 Instructions

**Purpose.** What the model must do.

**Rules.**
- Numbered list, ordered by importance
- Each instruction is **one** atomic action
- No compound instructions ("extract and classify and summarize")
- Imperative voice
- Total length ≤ 30 numbered items; longer prompts indicate a missing abstraction

### 3.4 Output Format

**Purpose.** Machine-readable contract.

**Rules.**
- JSON only (no free-form prose output for structured tasks)
- Inline schema in the prompt, using `jsonc` style with comments
- One example of valid output
- One example of "empty" output (e.g., `[]` for arrays)
- One example of "rejection" output if applicable

**Critical:** the schema in the prompt **must** match the schema in [04_data_schema.md](04_data_schema.md). Drift is a bug. If a prompt requires a different schema, it is the wrong schema.

### 3.5 Constraints

**Purpose.** What the model must never do.

**Rules.**
- Negative space is critical — most failures are from models doing too much
- Constraints are concrete and checkable
- Each constraint is one sentence

**Examples:**
- "Never invent a source URL. If the source is not in the input, do not emit a Signal."
- "Never assign a confidence above 0.5 unless the source is `regulatory_filing` or `earnings_call`."
- "Never use the word 'significant' without a number."

### 3.6 Examples

**Purpose.** Demonstrate the contract in action.

**Rules.**
- Minimum 3 examples per prompt: typical, edge case, rejection
- Each example has explicit "Input" and "Output" labels
- Examples must match the output schema exactly
- Examples should be drawn from real (anonymized) production cases, not fabricated

### 3.7 Anti-patterns

**Purpose.** Explicit "do not" list, complementary to Constraints.

**Rules.**
- Phrased as "Do not ..." (active prohibition)
- Each anti-pattern is something a model is **known to do** in this context
- Updated whenever a new failure mode is discovered

---

## 4. Prompt Authoring Rules

### 4.1 No Mystery Modifiers

Avoid vague intensifiers ("very", "extremely", "really"). They do not change model behavior in any predictable way.

### 4.2 Be Explicit About Format

If you want JSON, say "Return a JSON object". Do not say "return in JSON format" — that allows the model to wrap it in markdown code fences.

Add:
```
Output raw JSON only. Do not wrap in markdown code fences. Do not include commentary.
```

### 4.3 Chain-of-Thought vs Direct

Two styles:

**Direct (default for detection/scoring):**
```
Output: { ... schema ... }
```

**Chain-of-thought (for reasoning only):**
```
First, work through your reasoning in a "thinking" field.
Then, output the final JSON in a "result" field.

Example:
{
  "thinking": "...",
  "result": { ... }
}
```

Use chain-of-thought **only** when reasoning improves quality measurably. Reasoning prompts are expensive; do not use it reflexively.

### 4.4 Avoid Conflicting Instructions

Test prompts with conflict detection: scan for "always X" and "never X" where X is the same axis. These produce unpredictable behavior.

### 4.5 Token Budget Awareness

Every prompt should declare its expected token budget:
- Input budget: ≤ X tokens
- Output budget: ≤ Y tokens
- Reserved for examples: Z tokens (typically 30–40% of input budget)

A prompt that routinely exceeds its output budget is a bug. Set `max_tokens` defensively.

---

## 5. Prompt Versioning

Per [02 §7](02_agent_constitution.md), every prompt has a semver version.

- **MAJOR** — change to output schema, change of agent, change of role
- **MINOR** — new constraint, new example, wording clarification that affects behavior
- **PATCH** — typo fix, comment, formatting only

Old prompts are never deleted. They live in the prompt registry forever, for replay.

### Version Selection

The pipeline pins **exact** versions. `prompts/detector/extract_signals/v1.4.2.md` is what runs, never "latest."

A Signal's `provenance.prompt_versions` records the exact version used. Replay (`replay_cycle`) loads the same version.

---

## 6. Prompt Testing

### 6.1 Test Suite

Each prompt MUST have a test suite at:
```
prompts/<agent>/<purpose>/tests/
  case_01_typical.json
  case_02_edge.json
  case_03_reject.json
  ...
```

Each test case contains:
```json
{
  "name": "earnings beat typical",
  "input": { ... },
  "expected_output": { ... },
  "tolerance": {
    "exact_match_fields": ["type", "entity_ref.id", "direction"],
    "range_match_fields": {
      "score.magnitude": [0.4, 0.7]
    }
  }
}
```

### 6.2 Test Categories

| Category | What it covers |
|---|---|
| `typical` | Common, well-formed input |
| `edge` | Boundary conditions (very long, very short, ambiguous) |
| `reject` | Input that should NOT produce a Signal |
| `adversarial` | Designed to trick the model (e.g., planted false claims) |
| `regression` | Known failure mode from production that was fixed |

### 6.3 Test Execution

Tests run on:
- Every prompt change (CI gate)
- Every model upgrade (before promotion)
- Nightly, on a sampled production input set

A test failure on `regression` blocks deployment. A test failure on `adversarial` is acceptable if documented.

### 6.4 Quality Bar

A prompt is considered production-ready when:
- ≥ 95% pass rate on `typical`
- ≥ 90% pass rate on `edge`
- 100% pass rate on `regression`
- Brier score on `adversarial` ≤ 0.25

---

## 7. Prompt Anti-Patterns (Catalog)

These are recurring failure modes. Avoid them.

### 7.1 "Be Concise" Without a Token Budget

> "Be concise in your response."

Models interpret "concise" differently. Specify a char count or token count:
> "Keep the `one_liner` field under 140 characters."

### 7.2 "Use Your Judgment"

> "Use your judgment to determine significance."

This invites arbitrary outputs. Replace with a rubric:
> "Set `significance` per the rubric in [05 §2.1](05_reasoning_framework.md)."

### 7.3 Implicit Schema Changes

Changing the JSON shape in a prompt without bumping MAJOR. Always bump MAJOR on output-schema change.

### 7.4 Mixing Roles in One Prompt

> "First detect Signals, then score them, then summarize."

This is three agents, not one. Split into separate prompts.

### 7.5 Prompting With Examples That Conflict

If two examples in the prompt disagree on output format, the model will pick one. Audit examples for consistency before deployment.

### 7.6 Asking the Model to "Think Step by Step" Without a Structured Reasoning Section

This produces hidden reasoning that is not auditable. Either accept direct output, or use the explicit `thinking` field pattern (§4.3).

### 7.7 Burying Critical Instructions

Critical instructions (e.g., "Never invent sources") must be in the Constraints section, not buried in Instructions. Models weight sections differently.

---

## 8. Model Selection Per Task

Different tasks warrant different model tiers. Per P7 (cost-aware):

| Task | Recommended model | When to escalate |
|---|---|---|
| Boilerplate detection (skip LLM?) | None — use regex | n/a |
| Entity extraction | `claude-haiku-4-5-20251001` | If entity resolution rate < 95% |
| Type classification | `claude-haiku-4-5-20251001` | If F1 < 0.85 |
| Claim composition | `claude-opus-4-8` | (always) |
| Reasoning | `claude-opus-4-8` | (always) |
| Scoring dimensions | `claude-haiku-4-5-20251001` | If calibration degrades |
| Prose generation (reports) | `claude-opus-4-8` | (always) |

Escalation rule: if a task's quality metric drops below threshold on a tier, escalate one tier for one week and re-measure.

---

## 9. Prompt Registry

The registry is a single file:
```
prompts/registry.yaml
```

```yaml
agents:
  detector:
    extract_signals: v1.4.2
  verifier:
    check_source: v2.1.0
    check_quote: v1.0.3
  analyst:
    reason_significance: v0.3.1
    reason_causality: v0.3.1
    write_summary: v0.2.0
  scorer:
    score_dimensions: v1.2.0
  synthesizer:
    cluster_summary: v0.1.0
  reporter:
    daily_report: v1.0.0
    weekly_report: v0.9.0
```

This is the canonical "what runs in production." Pipeline reads this at boot.

---

## 10. Failure Recovery

When a prompt change causes a quality regression:

1. Identify the failing test cases
2. Either fix the prompt (and bump version) or roll back to previous version
3. Update `registry.yaml`
4. Re-score any in-flight Signals if schema changed (rare)

The pipeline supports a **shadow mode**: new prompt runs alongside old, scores are compared, no output published. This is the safe default for prompt changes.

---

## 11. Prompt Audit Trail

Every Signal's provenance records:
- `prompt_versions`: which prompt versions ran
- `model_versions`: which model handled each sub-task
- `temperature`: the sampling temperature (typically 0.0)
- `seed`: if the model supports it

This makes every Signal **reproducible** given the same inputs.

---

## 12. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Changes to required sections (§2, §3) are MAJOR. New anti-patterns in §7 or test categories in §6 are MINOR. Wording fixes are PATCH.