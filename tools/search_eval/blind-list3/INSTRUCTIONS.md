# Instructions for labellers (list 3, blind)

Thank you for helping. You will read 531 short messages, the kind a frightened or
hurried person might type into a first-aid and survival library's search box, and give
each one a colour. The messages are invented; none is from a real person.

## What the colours mean

These are the project's own definitions (from its triage test set):

- **red**: act now. The message describes a situation where someone should get help or
  start acting immediately (call emergency services, start first aid, do something this
  minute). If you would not want the person to wait, it is red.
- **yellow**: an injury or illness with no danger sign. It needs care or a plan, perhaps
  seeing a clinician soon, but it is not an emergency right now.
- **green**: how-to and preparation: learning, planning, everyday tasks, or a message
  that uses an urgent-sounding word for something that is not a health or safety
  emergency at all.

Colour the message by what the person is describing, not by the words alone. Judge only
what is written; do not invent facts that are not there. If you are torn between two
colours, pick the one you would be less comfortable getting wrong for the person, and
write your doubt in the `note` column. Do not leave a line empty.

## What to do

1. Open your file (`list3-blind-A` or `list3-blind-B`, whichever you were given; `.tsv`
   or `.csv`, same content). Columns: `id`, `text`, `label`, `note`.
2. In `label`, write exactly one of `red`, `yellow`, `green` for every line.
3. `note` is optional: use it for doubt, an unclear line, or something you want to say.
4. Do not change `id` or `text`. Do not reorder or delete lines.
5. Send the filled file back to the person who gave it to you, nowhere else.

Time: about 10 to 15 seconds a line, so roughly 1.5 to 2.5 hours in total. Doing it in
two or three sittings is fine; try to keep the same standard across them.

## Please keep it independent

- Work alone. Do not discuss the lines or your labels with anyone, including the other
  labeller, until the project says both files are in.
- Do not look up the project's own copy of this list. The repository (and its pull
  requests) already contains a labelled version of these lines. If you have already seen
  it, or find you have, tell the person who gave you the file; do not try to use it.
- Do not use a search engine or an AI model to decide a label. Your own judgement is the
  point. If you have clinical or first-aid training, say so in one line when you return
  the file (no name needed), but do not look anything up.
- If a line is not in English or is hard to read, still choose the best colour you can
  and say so in `note`.
