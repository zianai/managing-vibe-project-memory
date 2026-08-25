# Risk-Adaptive Human Alignment

## Goal

Human alignment prevents semantic drift without turning every task into ceremony. It is a reasoning lens, not a mandatory package tree.

| Level | Question |
|---|---|
| H0 | What outcome, boundary, non-goals, and evidence define this work? |
| H1 | Which choices remain autonomous, and which does the human reserve? |
| H2 | Has a material decision or consequence appeared that changes authority? |
| H3 | What changed, what remains, and must the human accept residual risk or preference? |

## Start Without Duplicate Ceremony

A clear current human instruction authorizes work within its visible scope when risk is low and reversible. Normalize it into the task boundary if durable continuity needs the fact; do not ask the human to reapprove your paraphrase.

For medium/high risk, expose the outcome, boundary, acceptance, principal consequences, and human-owned choices in a medium the human can understand before acting. Use exact versions or stable revisions only when ambiguity or staleness would matter. The protocol does not prescribe Markdown, HTML, JSON receipts, or a fixed gate count.

## Trigger H2 Only On Material Change

Pause for a human decision when:

- scope, acceptance, or risk increases;
- a confirmed key assumption fails;
- an irreversible, sensitive-data, production, security, financial, publication, message, legal, or other external consequence appears;
- implementation would materially deviate from a human-approved baseline;
- a genuine product-value choice remains undecided.

Do not pause for tool selection, code organization, test strategy, local diagnostics, reversible fixes, or another harness taking over the same confirmed work.

## Natural Decision Semantics

Ordinary language is sufficient when one current choice is visible and
unambiguous. “采用 A”, “okay”, or “可以” counts only after it is normalized as a
`direct-human-instruction` whose referent is that visible choice. Record the
conditions and what remains undecided.

These do not authorize an unseen or ambiguous boundary:

- generic “下一步”, “继续”, or silence;
- another agent’s summary that the human said yes;
- a test result or reviewer recommendation;
- a button/checkbox inside a review artifact;
- approval of another task, version, or decision.

Repository records are trusted project input, not identity authentication. Use external or signed attestation only when identity assurance is itself required.

## Durable Decision Record

Create a decision only if downstream work depends on it and the choice is not reliably derivable. Keep it compact:

```markdown
## <short stable decision name>

- Question: ...
- Decision: ...
- Subject: task, artifact revision, commit, or bounded proposal
- Scope/conditions: ...
- Not decided: ...
- Source: direct human instruction, verified review, or other explicit authority
```

Bind to a commit, patch, or stable artifact revision when later changes could invalidate the choice. A local Git commit already content-addresses its bytes; another digest is unnecessary. A provider URL must identify a fixed revision, not “latest”.

## Human Readout And H3

Present a human-readable result when it materially helps the owner understand the outcome, tradeoffs, proof, or next decision. Choose text, table, diagram, visual, demo, or another medium adaptively.

Exact H3 acceptance is required only for high-impact work, unresolved residual risk, material deviation/waiver, or when the human explicitly reserved completion acceptance. Ordinary low-risk completion does not require a separate acceptance round.

Always distinguish implemented, checks passed, independently verified, design preference approved, residual risk accepted, and target-user validated. Neither engineering verification nor an attractive artifact implies the others.
