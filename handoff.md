# Handoff — apply the Hackagotchi product-analysis playbook to **Kestrel** (GhostLabs)

> **Purpose.** This document hands a receiving agent the *exact methodology* used to analyze
> **Hackagotchi** (a GhostLabs hardware/firmware product) so it can reproduce the full analysis for
> **Kestrel**, another GhostLabs project. The Hackagotchi *findings* were product-specific; the
> *method* below is reusable. Worked examples to imitate live in the Hackagotchi repo:
> `docs/go-to-market.md`, `docs/monetization.md`, `case/CAT_ENCLOSURE_SPEC.md`, and the GPL-3.0
> relicense (`LICENSE` + `THIRD-PARTY-NOTICES.md`).
>
> **How to use:** read §1 (principles), do §2 (understand Kestrel + adapt), run §3 (the phases),
> ship §4 (deliverables). §5 has copy-paste lens templates. §6 has the hard-won defaults.

---

## 0. Operating mode

- **Best executed with multi-agent orchestration.** Each phase is a *fan-out of independent lenses*
  (run in parallel) → an *adversarial critic* that stress-tests all lenses together → a *synthesis*
  you write. If you have a Workflow/subagent tool, use it (parallel lenses + a high-effort critic).
  If you're a single agent, run each lens as its own sequential research pass, then the critic.
- **Ground everything in web research + the real repo.** Real comparables, real 2026 prices/fees,
  real numbers. Never vibes, never made-up figures.
- **You produce the synthesis.** Subagents return structured findings; *you* write the final docs and
  make the decisive calls. Don't just relay lens output.

---

## 1. Operating principles (non-negotiable — these are what made the analysis good)

1. **Adversarial verification at every phase.** End each phase with a ruthless critic prompted to
   *refute*: name the weakest/most wishful claims, what won't work, the single biggest risk, the
   honest odds, and a **cut list**. Trust the critic's corrected numbers over first-pass optimism.
2. **Honest ceilings.** Model the *realistic* outcome, not the fantasy. State the hard ceiling out
   loud (for Hackagotchi: "a beloved niche tool, not a viral phenomenon"). Treat breakout as a
   labeled lottery ticket that **never** enters a plan or anchors any spend.
3. **Lead with the core insight ("the wedge"), not the feature list.** Find the one-sentence,
   universally-felt pain the product resolves. That sentence *is* the positioning.
4. **Be decisive.** Pick winners and give numbers; don't survey options. Every recommendation states
   the action, the why, a confidence level, and (for money) the arithmetic.
5. **Separate "can" from "should."** Especially for licensing/closed-source: answer the legal
   question *and* the strategic question separately.
6. **Right altitude for the audience.** For a hobbyist/consumer/maker audience, the emotional hook /
   personality / mascot is the *primary* lever — lean in. For an enterprise/pro audience, firewall it
   and lead with credibility. Decide which Kestrel is *first*.
7. **Cross-link and date everything.** Each deliverable is a dated analysis snapshot, cross-linked to
   the others.

---

## 2. Phase 0 — Understand Kestrel, then ADAPT the plan (do this first)

Before any strategy work, build the shared brief every lens will reuse.

**Read the Kestrel repo end-to-end:** README, `docs/`, any roadmap/engineering notes, the code
structure, the license state, and every dependency's license. Determine:

- **What it is** and **who it's for** (the audience — and therefore the altitude per principle 6).
- **The core "wedge"/insight** — the one-sentence pain it kills.
- **Stage** — finished? still in development? (gates "launch now vs keep building").
- **Assets** — does it have a mascot/brand? hardware? 3D-printing capability? a community? a name with
  lineage/borrowed reach?
- **Licensing reality** — current license (or none = "all rights reserved"), and whether deps are
  permissive (MIT/BSD/Apache) or copyleft (GPL) / non-commercial (which constrains closing it).

**Then classify the project TYPE and adapt which phases apply:**

| Kestrel is… | Run | Adapt / skip |
|---|---|---|
| **Hardware / firmware product** | All of §3 incl. manufacturing + enclosure spec | — (the Hackagotchi case, verbatim shape) |
| **Pure software / app / SaaS** | §3 A, B, C, licensing | Replace "manufacturing/DFM" with *delivery/infra cost + COGS-per-user*; pricing vs software comparables; **skip** the enclosure spec (optionally produce a landing-page/brand spec instead) |
| **Dev tool / library / OSS** | §3 A, B (adoption-flavored), C, licensing | Monetization → OSS sustainability (sponsors, support, hosted/pro tier); virality → adoption/forkability; skip enclosure/manufacturing |
| **Service / content / other** | §3 A, C, licensing | Tailor B and the asset spec to the medium |

**Output of Phase 0:** a tight one-page **`{{KESTREL_BRIEF}}`** (product, wedge, audience, stage,
assets, license reality, the goal). Every lens prompt below interpolates it. This mirrors the
`BRIEF` constant used in the Hackagotchi workflows.

---

## 3. The analysis phases

Each phase = fan-out lenses → adversarial critic → your synthesis into one dated doc.

### Phase A — Go-to-market / marketing strategy → `docs/go-to-market.md`
**Lenses:** (1) audience & channels — *who*, ranked, with the beachhead, and the exact 2026
communities/channels to reach them; (2) positioning & messaging — the 5-second one-liner, taglines,
the narrative (pain → villain → hero), naming check; (3) launch playbook — sequenced, the single best
lead surface, the one make-or-break asset; (4) competitive landscape — real alternatives + prices,
the defensible differentiation, where *not* to fight; (5) business model — monetization shape +
channels; (6) content & assets — the highest-leverage pieces, ranked by impact-per-effort.
**Critic:** the real wedge, weakest claims, what won't work for a small/solo team, biggest risk, the
**cut list**, and an honest "product vs portfolio/credibility play" verdict.

### Phase B — Virality / adoption strategy → fold into `docs/go-to-market.md`
**Lenses:** (1) **viral case studies** — find the *real* analogues that went viral in Kestrel's space
and extract the repeatable mechanics (for Hackagotchi: Pwnagotchi, Flipper, the deauther,
Meshtastic); (2) the **hook** — the emotional/mascot/personality lever or the "money moment" that is
inherently shareable; (3) **channel ignition mechanics** — what actually triggers a front page /
algorithm / share cascade, and the firing *order* (e.g. Reddit warm-up → Hackaday amplifier → hold
Show HN); (4) the **distribution funnel** — hardware: 3D-print + build-it-yourself; software:
free-tier/templates/integrations/forkability; (5) **licensing-for-virality** — open vs closed, and
its effect on the community flywheel; (6) **timing & readiness** — launch-now vs keep-building, the
readiness minimum, a realistic definition of "viral" for this niche (tiered, with odds).
**Critic:** the single **ignition move**, the **honest odds**, what *kills* virality, and the decisive
open/closed call.

### Phase C — Monetization, pricing & manufacturing/delivery → `docs/monetization.md`
**Lenses:** (1) revenue model + **the actual math** — every stream ranked by contribution, the funnel
math (visitors → conversion → paid), unit economics, and **low/base/high 12-month scenarios** with
explicit assumptions; (2) **pricing market analysis** — competitor price map, willingness-to-pay
floor/ceiling, the recommended price ladder (good/better/best) with rationale; (3) **manufacturing /
DFM** (hardware) — enclosure (FDM → POD → injection-mold break-evens), electronics (COTS vs custom
PCB MOQ curves), certification, assembly — *or* **delivery/infra cost** (software); (4) **channel
economics** — fees, fulfillment burden, tax/VAT handling, and crowdfunding-to-de-risk-the-first-run.
**Critic (CFO-style, high effort):** the weakest numbers (haircut them), a frank **realistic P&L**
(is this a business, side-income, or break-even hobby?), the **biggest financial risk**, a
sell-or-not verdict, the **recommended sequenced path**, and a **cut list**. *The critic's corrected
numbers are the ones you publish.*

### Cross-cutting 1 — Licensing decision (+ optionally execute it)
Answer both questions: **CAN** it be closed (audit every dependency's license — flag any
copyleft/non-commercial traps) and **SHOULD** it (strategy: for clonable/community products the moat
is brand + docs + convenience + trademark, not the bytes → usually **open-core**). Recommend a
specific license + the open-core structure. If asked to execute: add `LICENSE` + per-file SPDX
headers + a root `THIRD-PARTY-NOTICES.md`, kill any stale license references, **on a branch → PR**.
(Hackagotchi precedent: GPL-3.0 for the project, MIT kept on a subtree that's a fork of an MIT
upstream to preserve upstream-ability. Confirm the copyright holder against the **GitHub org name**,
not a guess.)

### Cross-cutting 2 — Tangible-asset spec (if applicable)
Hardware → an enclosure/industrial-design spec + a ready-to-use **CAD-agent prompt** (see
`case/CAT_ENCLOSURE_SPEC.md` for the shape: design thesis, hardware-to-house with `[MEASURE]`
parametric placeholders, feature→form mapping table, print constraints, deliverables, and the
self-contained prompt). Software → a landing-page / brand / onboarding spec.

---

## 4. Deliverables

Produce, each on its **own branch → PR** (keep PRs focused; docs-only PRs separate from any code/
license change):

- `docs/go-to-market.md` — GTM + virality (audience, positioning, the ignition move, channel
  sequence, the **honest ceiling** table, what-kills-it, the readiness gate, a **cut list**).
- `docs/monetization.md` (or `docs/business-model.md` for software) — the **corrected** money math,
  pricing ladder, unit economics, scenario table, the cardinal financial rules, manufacturing/
  delivery roadmap, channel sequence, the pre-revenue gate.
- (hardware) `<dir>/<ASSET>_SPEC.md` — asset spec + CAD-agent prompt.
- Licensing: `LICENSE` + `THIRD-PARTY-NOTICES.md` (if executing) on a relicense branch → PR.

**Delivery (pre-authorized by Davis — don't ask for this part).** When a phase's report/deliverable
is finished, ship it end-to-end: **commit → push → open PR → sync with `main`** (merge the PR, then
update local `main`). This delivery flow is standing-authorized. You still **pause between phases**
for steering, and still **ask before** anything destructive/out-of-scope (force-push, history
rewrite, deleting work) and before any **license change** not already cleared with Davis.

**Every doc:** dated header + one-line provenance, evidence-grounded, the critic's corrected figures,
cross-linked, and an explicit "honest ceiling" + "cut list".

---

## 5. Reusable templates (copy-paste; substitute `{{KESTREL_BRIEF}}`)

**Lens output schema (structured):**
```
{ lens: string,
  keyFindings: string[],                 // 4–7 decisive, evidence-backed
  numbers?: string[],                    // concrete figures w/ sources (money phases)
  recommendations: [{ action, why|rationale, priority|viralLeverage|confidence, effort? }],
  evidence?: string[] }                  // named cases, URLs, prices, mechanics
```

**Critic output schema:**
```
{ weakestClaims: string[], whatWontWork|whatKills: string[], biggestRisk: string,
  theRealWedge|theIgnitionMove: string, honestOdds|realisticPnL: string,
  decisiveCall: string,                  // e.g. open/closed, sell-or-not, product-vs-portfolio
  cutList: string[] }
```

**Generic lens prompt:**
```
You are a {{ROLE}} for {{PROJECT TYPE}}. {{TASK FOR THIS LENS}}.
{{KESTREL_BRIEF}}
Use WebSearch to ground this in current (2026) reality. Be specific with NAMES, NUMBERS, and real
comparables — not categories. Deliver {{the bullet list of what this lens must produce}}. Be
opinionated and pick winners; show arithmetic where relevant.
```

**Adversarial critic prompt:**
```
You are a ruthless {{growth / CFO}} advisor doing a REALITY CHECK on the strategy assembled for
{{PROJECT}}. Be adversarial and decisive — stop a small team from wasting months/money.
{{KESTREL_BRIEF}}
Assembled findings from the lenses (JSON): {{LENSES_JSON}}
Identify: the weakest/most wishful claims; what won't work for a small team with no budget/audience;
the single biggest risk; THE one move that matters most (be concrete); the honest odds / realistic
P&L (don't flatter); the decisive call ({{open vs closed / sell-or-not / etc.}}); and the cut list of
what to NOT do.
```

**Phase lens menus** (interpolate the brief into each): use the lens lists in §3 A/B/C verbatim as the
set of parallel lenses per phase.

---

## 6. Hard-won defaults from Hackagotchi (apply, but re-verify for Kestrel)

- **Open-core beats closed** for clonable / community / maker products. Closing the source on a
  commodity base protects almost nothing and kills the fork/plugin/community flywheel. Monetize the
  brand, docs, convenience, trademark, and a premium tier — never the bytes. *(Verify Kestrel's
  audience expects openness before assuming this.)*
- **Plan for the niche base case, not the lottery.** Breakout is a 10–20%-at-best upside that must
  never appear in a P&L.
- **Price for after-labor margin.** For small-batch hardware, *labor — not BOM —* is the margin
  killer; price above the "nets ~$0 after your time" floor. For software, watch infra COGS + support
  load per user.
- **Never spend tooling/inventory ahead of validated demand** — crowdfund the first real run.
- **Never ship without the safety/quality basics** (hardware: input protection; software: the
  equivalent first-run/data-loss guards) — RMAs/churn erase all margin and the brand.
- **The mascot/personality can be the #1 viral lever for a hobbyist audience** — but firewall it from
  capability claims for a pro/enterprise audience.
- **Lineage/borrowed reach is free** — if the name or category rides an existing beloved thing, state
  it explicitly.

---

### Quick-start for the receiving agent
1. Read this whole file. 2. Do **Phase 0** → write `{{KESTREL_BRIEF}}` and classify the project type.
3. Run **Phase A**, then **B**, then **C** (fan-out lenses → critic → synthesize), pausing after each
   to let the human steer. 4. Do the **licensing** decision; execute it on a branch + PR if asked.
5. Produce the **asset spec** if applicable. 6. For each finished deliverable, **commit → push → open
   PR → sync with `main`** (pre-authorized — don't ask).
Pause between phases for steering and surface conflicts; ask before anything destructive/out-of-scope
or any **license change** not yet cleared with Davis.
