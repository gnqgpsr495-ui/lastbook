# Protocol: blind labelling of list 3

Status: prepared, not started. No outside label exists yet.

## What list 3 is, and why it needs this

List 3 is a held-out set of 531 invented urgency-test lines: 199 red, 78 yellow, 254
green (147 of the green are everyday lines that contain urgent-sounding words). It has not
been used to build or tune anything. Its labels, however, were written by the same agent
that wrote the lines. This protocol replaces them, as the reference, with labels from
independent people.

The labelled list (`tools/search_eval/lists/list3.jsonl`) is already public in the
repository, on the triage branches and in the open pull requests, so blindness here
depends on the labellers not looking, and on them telling us if they did (see
INSTRUCTIONS.md). The commitment (COMMITMENT.md) shows the key was fixed before any
outside label existed. It does not hide the labels.

## Procedure

1. **Files.** Each line has a random ID (`secrets.token_hex(4)`). Two independent
   shuffles of the same lines were drawn with `secrets.SystemRandom().shuffle` (the
   operating system's cryptographic random source): `list3-blind-A` and `list3-blind-B`.
   Both are published. They carry the ID and the text only: no original label, colour,
   group or source. Nothing is seeded, so the draws cannot be repeated, only inspected.
2. **Who labels.** Two people per line, working alone: labeller 1 gets file A, labeller 2
   gets file B. Neither sees our labels, the other's labels, or the search results. The
   different order guards against order and fatigue effects. Volunteers say in one line
   whether they have first-aid or clinical training; no names are published.
3. **Commitment.** The key (ID, line number in the source, our label, group) is private
   until both labelled files are in. Its SHA-256 is in COMMITMENT.md.
4. **Agreement.** Computed by `agreement.py` (pure Python, self-tested). Reported as
   raw percent agreement, the 3x3 table, and Cohen's kappa with a 95% confidence interval
   (percentile bootstrap over lines, 2,000 resamples, fixed seed).
   - **Primary: linearly weighted kappa**, because red, yellow and green are ordered and
     red-versus-green is a larger mistake than red-versus-yellow.
   - Also reported: unweighted kappa, and kappa for red versus not red (the split that
     matters for missing an emergency).
5. **Disagreements.** A third person, who has seen neither labeller's file, gets only the
   disagreeing lines with the two labels (shown in colour order, so the labeller
   cannot be told apart) and the line. They choose a final label and may note why. Our
   labels are never shown to them. Every adjudication is recorded with both original
   labels (`adjudications.tsv`).
6. **Consensus.** The reference label for a line is the shared label if the two agreed,
   otherwise the adjudicated one. Only then is the key published, after checking its hash.
7. **What is then measured.** Our original labels against the consensus (same statistics),
   each labeller against the consensus, and the search's red recall and green false-flag
   rate rescored against the consensus labels, with Wilson 95% intervals. If the numbers
   differ from those reported on our own labels, both are shown.
8. **No tuning.** List 3 stays out of every tuning step, before and after labelling.
   Nothing about the search changes because of what the relabelling shows; it is reported
   as it is. If a labeller drops out, a replacement labels the same file; we say so.

## Second held-out set for first-page claims (plan, not done)

List 3 tests urgency only. A claim about which page appears first needs a different set.
This is a plan; none of it has been done.

- **Set.** A new set of questions, written before any engine is run on it, not used for
  tuning.
- **Who chooses.** For each question, people independently choose the pages or passages
  they consider useful, from the library, before seeing any search result. Two people per
  question; a third settles disagreements, same as above. The agreed choices are the
  reference.
- **Blinding.** Candidates are shown in a neutral order, without saying which engine
  (keyword, meaning, or a later change) returned what, and results are scored against
  the fixed reference afterwards.
- **How many questions.** For a proportion such as "first page is useful", a 95% Wilson
  interval is about +-10 percentage points wide at 96 questions (worst case p = 0.5:
  1.96 x sqrt(0.25 / 96) = 0.100). So about 96 questions per group that is reported
  separately (for example red questions, and everyday questions). Smaller groups are
  reported with their wider intervals. (A before/after comparison on the same questions
  needs its own estimate; this one is for a single proportion.)
- **Reporting.** First page useful and no useful page in the top 8, per group, with
  intervals; before/after comparisons on the same questions use the paired exact test
  already in `tools/search_eval/stats.py`.

## A new held-out urgency list (List 5), written by someone else (plan only)

Even with blind labels, List 3 has two limits:
- Its lines were written by the same model family as Lists 1 and 2. List 4 came from another family (Qwen3.5-9B, run locally; see the README).
- Its labels are public.

A truly unseen test needs a new list (List 5), written by someone other than the author of this proposal: a person, or a model from neither of those families. It would stay private until the search has been run on it, with only its SHA-256 posted on #401 first. Here is an example prompt for anyone who wants to generate it with a model; editing it is welcome:

```
Write 500 short messages that a person might type into the offline search box of an
emergency and survival library, with no internet and no one to call. Mix:
- about 35% RED: someone is in danger right now (not breathing, heavy bleeding,
  unconscious, chest pain, choking, severe allergic reaction, stroke signs, suicide
  or self-harm, poisoning, drowning, a child or baby in danger, ...);
- about 15% YELLOW: an injury or illness that needs care but has no danger sign;
- about 50% GREEN: how-to and preparation questions. At least half of these must be
  everyday messages that use urgent-sounding words without any emergency
  ("my sourdough starter died", "killer workout for legs", "my phone battery is dying").
Vary the writers: age, panic level, spelling (typos, no spaces, no punctuation, text
speak), length (2 to 25 words), first or third person, and about 10% in Spanish and
other languages. Don't repeat a situation in different words more than twice.
Output JSON Lines, one object per line: {"text": ..., "triage": "red"|"yellow"|"green"}.
```

If you make one, please keep the file to yourself, post only its SHA-256 on #401, and say which model you used (or that it was written by hand). The search is then run on it and reported before anyone opens it.
