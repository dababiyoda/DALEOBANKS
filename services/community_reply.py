"""Pure bounded simulated response used by FeedbackService and Generator."""
import json
PREFIX = 'SIMULATED_VERIFIED_CORRECTION:'
ABSTAIN = 'I do not have a verified answer; please provide a source.'


def supported_reply(topic, notes, sources):
    facts = set()
    for note in notes:
        if not isinstance(note,str) or not note.startswith(PREFIX):
            continue
        try:
            correction=json.loads(note[len(PREFIX):]); source=sources[correction['source_id']]
            if correction['topic']==topic==source['topic'] and correction['fact']==source['fact']:
                facts.add(source['fact'])
        except (KeyError,TypeError,ValueError):
            continue
    return next(iter(facts)) if len(facts)==1 else ABSTAIN
