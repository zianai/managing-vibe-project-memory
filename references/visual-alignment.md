# Adaptive Visual Alignment

## Activate Only When Useful

Use this overlay when the human reserves aesthetic or experience preference; navigation, information architecture, interaction, or product meaning is genuinely undecided; implementation would create high sunk cost before visual misunderstanding is found; work claims conformance to an approved design; or UI controls privacy, safety, deletion, payment, publication, messaging, or another consequential action.

Do not force it for every UI file. It may be unnecessary for a disposable prototype, a mechanical fix inside an approved system, a local reversible tweak, work with no visible change, or explicit delegation of design judgment to the agent.

## Choose Medium And Depth Adaptively

Use the smallest medium that makes the real decision inspectable: a project-local Figma export, image, PDF, video, HTML, native preview/demo capture, manifest, or composite; alternatively use a stable immutable provider-revision subject. No medium or fixed gate count is universally authoritative.

Use L1–L5 as questions, not mandatory gates:

| Level | Makes inspectable |
|---|---|
| L1 | user journey and state transitions |
| L2 | page relationships, navigation, information priority |
| L3 | complete normal and important exceptional states |
| L4 | hierarchy, density, copy, appearance, interaction, accessibility |
| L5 | approved baseline compared with a real implementation render |

One artifact may cover several levels. Split experience and visual reviews only when doing so materially reduces misunderstanding. A new page does not mechanically require two approvals.

A durable visual baseline must actually expose the claimed visual or interaction decision; prose describing a screen is not a visual baseline. A provider artifact needs a fixed revision and exact frame/node scope. Keep a local export when provider-less recovery matters. A mutable external link may appear only as context through a project-local note; it is not authority.

When activated, the task always names stable `approved_baseline_subject` and
`implementation_render_subject`, plus a substantive `baseline_decision_ref` and
`conformance_status`. An immutable provider/artifact subject that includes its
revision and exact frame, node, page, or capture scope may stand alone; its
project-local `approved_baseline_ref` or `implementation_render_ref` is an
optional recovery/context export. A `sha256:` or other local-byte subject must
have the matching project-local ref. Mutable provider URLs remain context only
through a local note. A checker can validate stable identity shape, local
reference containment, and record consistency; it cannot judge aesthetics,
prove provider provenance, or prove that an artifact communicates its claimed
meaning.

## Decisions

Before expensive implementation, expose the unresolved human-owned choice and state what the decision would and would not authorize. Natural confirmation is valid only after it is normalized as a direct human instruction with one unambiguous current referent. Record a substantive decision, its subject/revision, scope, conditions, and what remains undecided.

If the human delegates design, record that boundary and let the agent exercise current design capability. Describe the result as agent-designed unless the human later approves it.

## Conformance

When an approved baseline exists, compare it with a durable capture of the real
implementation render. A conformance claim requires a substantive task
`review_ref` whose exact subject is current; that formal review binds front-matter
`baseline_subject` and `implementation_render_subject` to the exact task values,
then records pages/states and environment, material differences and disposition,
and limitations.

Source code, snapshot-test success, or a mockup alone cannot prove rendered conformance. HTML can be a capable baseline only when it exposes actual visual structure; HTML is not itself a runtime implementation render. If rendering is unavailable, state that conformance was not verified. Without a human-approved baseline, do not claim approved conformance.

Engineering correctness, human aesthetic preference, accessibility verification, and target-user validation remain separate conclusions. A changed baseline revision or implementation subject invalidates only the affected comparison/approval.
