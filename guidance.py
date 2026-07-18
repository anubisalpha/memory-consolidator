"""Human-facing guidance for finding categories, so a report is never just a
list of warnings with no next step.

Split into two dicts because they mean different things to a reader:
AUTO_FIXABLE explains how the tool resolves it for you (a rules.md flag to
flip, or a review command to run) — see fixer.py's module docstring for what
each flag actually does. GUIDANCE covers everything the tool can only detect,
never fix — each entry is the concrete manual next step, not just a
restatement of the finding.

Consulted by report.py (prints once per category present, not once per
finding, to avoid drowning a report in repeated text) and by main.py's
`triage` command (walks through GUIDANCE categories one at a time; a
category NOT in GUIDANCE is intentionally excluded from triage since it
already has its own resolution path — full_auto or review-findings)."""

AUTO_FIXABLE = {
    "dead_link": "Auto-fixable — enable automation.auto_fix_broken_links in rules.md and run `audit`.",
    "orphan": "Auto-fixable — enable automation.auto_fix_missing_index_entries in rules.md and run `audit`.",
    "stale": "Partially auto-fixable — full_auto's auto_fix_mark_stale flags it visibly in the file, "
             "but you still need to verify/update the actual content by hand.",
    "duplicate": "Exact duplicates are auto-fixable (auto_fix_merge_exact_duplicates, full_auto only). "
                 "Near-duplicates need a human judgment call — run `review-findings` to triage them.",
    "slug_hygiene": "Auto-fixable — enable automation.auto_fix_slug_mismatch in rules.md (full_auto only) and run `audit`.",
}

GUIDANCE = {
    "malformed": "Fix the YAML/frontmatter by hand — a `---` block failed to parse. Check for tabs, "
                 "an unquoted value containing a colon, or a missing closing `---`.",
    "duplicate_slug": "Two files claim the same `name:`. Rename one to a distinct slug, or if they're "
                       "genuinely the same concept, merge them by hand and delete the other.",
    "external_pointer": "This pointer-only memory's target file wasn't found. Update the path it points "
                         "to, or remove the pointer if the content moved or was deleted.",
    "index_size": "MEMORY.md is over the line-count limit. Consolidate or retire older entries — see "
                  "the project's index-truncation convention.",
    "broken_wikilink": "This [[wikilink]] doesn't match any file's `name:`. Either the target was "
                        "renamed/deleted (update or remove the link) or it's a typo (fix the link text).",
    "invalid_type": "metadata.type must be one of user/feedback/project/reference. Run `triage` to pick "
                     "the right one interactively, or edit the file by hand.",
    "frontmatter": "Frontmatter is missing a required field. Add it by hand — see the memory-authoring "
                   "spec (name/description/metadata.type).",
    "frontmatter_type": "A frontmatter field has the wrong type — often YAML silently coercing an "
                         "unquoted value into a date/number/bool. Quote the value so it stays a string.",
    "index_line_length": "This MEMORY.md line is too long. Shorten the description while keeping the "
                          "link and the core hook — don't just truncate mid-sentence.",
    "why_how_structure": "Add the missing **Why:**/**How to apply:** section(s) — required for "
                          "feedback/project types per the memory-authoring spec.",
    "file_length": "This file's body is long. Consider splitting into a pointer + a separate detail "
                   "file, or trimming to the parts still relevant.",
    "description_quality": "The description is too short or too generic. Write one specific enough "
                            "that a future session can tell at a glance whether this memory is relevant.",
    "code_derivable": "This content looks derivable straight from code (exact paths, function names). "
                       "Consider whether it belongs in a memory at all, or just a code comment.",
    "duplicate_check_skipped": "Too many files in this area for pairwise duplicate comparison "
                                "(see duplicate_detection.max_files_for_pairwise) — duplicate detection "
                                "was skipped here, not resolved.",
}


def guidance_for(category: str) -> str:
    return AUTO_FIXABLE.get(category) or GUIDANCE.get(category) or (
        "No guidance recorded for this finding category yet — treat it as a manual judgment call."
    )
