"""Phrase matching without character bigrams.

Vocabulary comes from glossary terms and their aliases, tags, symbols, title phrases split on
punctuation and whitespace, and the words of an entry's file name. Task text is scanned for the
longest phrases first; each phrase counts once and a matched span cannot be reused by a shorter one.
"""
import re
import unicodedata

SPLIT = re.compile(r'[\s,，。.;；:：、/|（）()\[\]【】「」“”"\'!?！？·<>《》]+')
WORD = re.compile(r'[a-z0-9_]')
STOP = frozenset({'and', 'for', 'the', 'with', 'from', 'into', 'not', 'are'})


def normalize(text):
    return unicodedata.normalize('NFKC', text).lower()


def is_ascii(phrase):
    return phrase.isascii()


def title_phrases(text):
    out = set()
    for part in SPLIT.split(normalize(text)):
        part = part.strip('-_.')
        if is_ascii(part):
            if len(part) >= 3 and re.search('[a-z]', part) and part not in STOP:
                out.add(part)
        elif len(part) >= 2:
            out.add(part)
    return out


def slug_words(ref):
    stem = ref.rsplit('/', 1)[-1].removesuffix('.md')
    stem = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', stem)
    return {w for w in stem.split('-') if len(w) >= 3 and w not in STOP and re.search('[a-z]', w)}


def term(phrase):
    """A curated phrase (tag, symbol, glossary term) used whole."""
    phrase = normalize(phrase).strip()
    return phrase if len(phrase) >= 2 else ''


def find(text, vocabulary):
    """Return the set of vocabulary phrases found in `text`, longest first, without overlapping reuse."""
    norm = normalize(text)
    taken = [False] * len(norm)
    hits = set()
    for phrase in sorted(vocabulary, key=lambda p: (-len(p), p)):
        start = 0
        while True:
            index = norm.find(phrase, start)
            if index < 0:
                break
            end = index + len(phrase)
            bounded = not is_ascii(phrase) or (
                (index == 0 or not WORD.match(norm[index - 1])) and (end == len(norm) or not WORD.match(norm[end])))
            if bounded and not any(taken[index:end]):
                for position in range(index, end):
                    taken[position] = True
                hits.add(phrase)
                break
            start = index + 1
    return hits
