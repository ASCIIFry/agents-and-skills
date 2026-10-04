---
name: requirements
description: Method and org template for a requirements spec (goal, scope, REQ/NFR IDs with acceptance criteria). Use before planning a new project or a large, unclear feature.
---

# Requirements specification

The goal is a specification that a planner can turn into work packages and
a verifier can check, with as few questions to the user as possible.

## Process
1. *Understand*: read the request, the existing code, README and docs. Note
   what the system does today and who uses it.
2. *Draft*: fill the template below. Write what is needed, not how to build it.
3. *Find gaps*: go through the quality checklist and the requirement rules.
   Look for contradictions, missing users or flows, error and edge cases,
   unclear limits, and unstated "done" conditions.
4. *Ask or assume*: ask only where the answer changes scope, effort, risk or
   architecture. Otherwise pick the sensible default and record it under
   Assumptions. At most 5 questions per round, at most 2 rounds.
5. *Finalise*: work the answers in, move what stays unclear to Assumptions
   or Open points, and add a change-log entry.

When `docs/requirements.org` already exists, update it: keep existing IDs,
give new requirements new IDs, mark dropped ones `RETIRED` instead of
deleting or reusing them, and log the change.

## Rules for each requirement
- One requirement per ID, phrased as "The system shall …" or as a user
  story ("As a <role> I want <capability> so that <benefit>").
- Testable: at least one acceptance criterion in Given / When / Then form,
  with concrete values instead of "fast", "secure" or "user-friendly".
- Solution-free unless the user fixed the solution (then it is a constraint).
- Prioritised with MoSCoW: MUST, SHOULD, COULD, WON'T (this time).
- Traceable: a stable ID (`REQ-001` functional, `NFR-001` quality) and a
  source (user request, existing behaviour, regulation, assumption).

## Quality checklist (NFRs)
Consider each item and write a requirement only where it matters:
- Security: authentication, authorisation, secrets, input handling, audit logging.
- Privacy: personal data, GDPR basis, retention, deletion, data location.
- Reliability: availability, recovery, data loss tolerance, backups.
- Performance: response times, throughput, data volumes, limits.
- Operability: deployment, configuration, monitoring, logging, cost.
- Maintainability: tests, code standards, dependencies, documentation.
- Compatibility: platforms, versions, interfaces, migration of existing data.
- Usability and accessibility: target users, languages, accessibility needs.
- Compliance and legal: licences, contracts, industry rules.

## Questions for the user
Each question goes into the result as:
```
Q1: <the question, one sentence>
    Why: <what it decides>
    Options: <recommended option> (recommended) | <option> | <option>
```
Use 2–4 options with labels of a few words, so the question can be answered on a phone.

## Template (docs/requirements.org)
```org
#+TITLE: Requirements: <project>
#+DATE: <YYYY-MM-DD>

* Goal
<One paragraph: the problem, who has it, and what changes when it is solved.>

* Scope
** In scope
** Non-goals

* Stakeholders and users
| Role | Need | Involvement |
|------+------+-------------|

* Functional requirements
** REQ-001 <short title>
*Priority:* MUST · *Source:* <user request | existing behaviour | A-1 | …> · *Status:* proposed

<The system shall … / As a … I want … so that …>
- AC1: Given … When … Then …

* Quality requirements
** NFR-001 <short title>
*Priority:* SHOULD · *Source:* <…> · *Status:* proposed

<Measurable statement.>
- AC1: …

* Constraints
* Assumptions
- A-1: <assumption>, because <reason>. Revisit if <condition>.

* Risks
| Risk | Impact | Mitigation |
|------+--------+------------|

* Open points

* Change log
| Date | Change |
|------+--------|
```
Keep the metadata on one line directly below each heading, so it also shows
in the Markdown copy. Once the user approves the specification, every
`*Status:* proposed` becomes `*Status:* approved`. Link to other headings in the file with `[[Heading]]`. Write
the specification in the language the user writes in.
