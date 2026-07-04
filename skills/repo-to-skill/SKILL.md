---
name: repo-to-skill
description: Generate callable agent skills from a local repository and a user goal.
---

# repo-to-skill

Use this skill when a user gives you a local repository and a goal, and wants the
right existing APIs turned into callable agent skills.

Core promise:

> Give it a repo and a user goal. It finds the right APIs and turns them into callable agent skills.

## When to use

- The user has a legacy or internal codebase with HTTP APIs.
- The user wants a focused callable skill for a business goal, not a generic repo map.
- The goal needs live behavior from the existing system rather than reimplementing logic.

## Workflow

1. Analyze the target repository without modifying it:

   ```bash
   repo-to-skill analyze <repo> --output <workdir>/analysis
   ```

2. Inspect `<workdir>/analysis/callable_capabilities.json`.

   Focus on each interface's `slug`, `route`, `handler_symbol`, `business_method`,
   request fields, response fields, and safety notes.

3. Translate the user's goal into a small set of relevant interface slugs.

   Prefer 3-20 APIs. Choose fewer if the goal is narrow. Do not invent slugs;
   every slug must appear in `callable_capabilities.json`.

4. Write a selection file:

   ```json
   {
     "need_summary": "Generate a callable skill for the user's concrete goal.",
     "selected_slugs": ["first-slug", "second-slug"],
     "selection_source": "agentic"
   }
   ```

5. Generate one bundle skill:

   ```bash
   repo-to-skill generate <repo> \
     --analysis <workdir>/analysis \
     --output <workdir>/skill \
     --mode callable-bundle \
     --selection-json <workdir>/selection.json
   ```

   If you cannot confidently select slugs, let repo-to-skill use its deterministic
   fallback:

   ```bash
   repo-to-skill generate <repo> \
     --analysis <workdir>/analysis \
     --output <workdir>/skill \
     --mode callable-bundle \
     --need "<user goal>" \
     --max-interfaces 12
   ```

6. Validate the generated bundle:

   ```bash
   repo-to-skill validate <workdir>/skill/<bundle-name>
   ```

## Output expectations

A callable bundle is one skill directory containing:

- `SKILL.md`
- `manifest.yaml`
- `tools/*.tool.yaml` for the selected APIs
- `scripts/call_*.py` callers for the selected APIs
- `references/capability-selection.md` explaining why each API was selected
- `references/capability-source.md` mapping tools back to source routes, handlers,
  business methods, and contract fields

## Mode: task-workflow

Use when the goal maps to a **predefined** workflow (count-then-list, single read-only query) rather than an ad-hoc API chain. Provide `--workflow-hints <hints.json>` and `--need "<goal>"`. v1 supports `single-query` and `count-list-query` only. See `docs/skill-reference.md` for the hints schema and the generated layout.

## Output language

repo-to-skill decides the prose language (headings, labels, explanations in
`SKILL.md` and `references/*.md`) from the `--language` option:

- `--language auto` (default): detect from the goal/need text. If CJK characters
  make up at least 30% of non-whitespace characters, the output is `zh-CN`;
  otherwise it is `en`.
- `--language zh-CN` or `--language en`: override detection explicitly.

Source-derived identifiers (slugs, routes, handler symbols, business method
names, field names, `# TODO` markers) are never translated — they must stay
faithful to the wire contract.

```bash
repo-to-skill generate <repo> \
  --analysis <workdir>/analysis \
  --output <workdir>/skill \
  --mode callable-bundle \
  --need "<user goal in any language>" \
  --language auto
```

## Safety rules

- Do not modify the target repository.
- Do not hard-code endpoints or tokens.
- Do not put local machine paths, private URLs, or credentials into the generated skill.
- Generated callers preview by default. They only call a live system when the user
  sets the endpoint environment variable and passes `--execute`.
- If an interface has side effects or unclear behavior, preserve that uncertainty
  in the final explanation instead of overselling it.
