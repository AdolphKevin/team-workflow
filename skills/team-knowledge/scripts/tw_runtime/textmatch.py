"""BM25 ranking with ASCII words and adjacent Han characters.

Glossary terms and abandoned approaches retain longest-first, non-overlapping phrase matching.
"""
from collections import Counter
import math
import re
import unicodedata

SPLIT = re.compile(r'[\s,，。.;；:：、/|（）()\[\]【】「」“”"\'!?！？·<>《》]+')
WORD = re.compile(r'[a-z0-9_]')
RUN = re.compile(r'[a-z0-9_]+|[〇々㐀-䶿一-鿿豈-﫿\U00020000-\U000323AF]+')
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


def token_runs(text):
    for run in RUN.findall(normalize(text)):
        if not run.isascii():
            yield [run[i:i + 2] for i in range(len(run) - 1)]
        elif len(run) >= 2 and run not in STOP and (not run.isdigit() or len(run) >= 3):
            yield [run]


def tokens(text):
    return (token for run in token_runs(text) for token in run)


def matched_words(runs, shared, idf):
    words = {}
    for run in runs:
        start = 0
        while start < len(run):
            if run[start] not in shared:
                start += 1
                continue
            end = start + 1
            while end < len(run) and run[end] in shared:
                end += 1
            phrase = run[start] + ''.join(token[-1] for token in run[start + 1:end])
            words[phrase] = sum(idf[token] for token in run[start:end])
            start = end
    return sorted(words, key=lambda word: -words[word])[:3]


def rank(task, frequencies):
    """Return scores and evidence by document label, using the entire corpus for statistics."""
    runs = list(token_runs(task))
    query = sorted({token for run in runs for token in run})
    if not query or not frequencies:
        return {}
    lengths = {label: sum(counts.values()) for label, counts in frequencies.items()}
    size = len(frequencies)
    average = sum(lengths.values()) / size
    df = Counter(token for counts in frequencies.values() for token in query if token in counts)
    idf = {token: math.log(1 + (size - count + 0.5) / (count + 0.5)) for token, count in df.items()}
    k1, b = 1.2, 0.75
    scores = {}
    for label, counts in frequencies.items():
        shared = {token: counts[token] for token in query if token in counts}
        if shared:
            norm = k1 * (1 - b + b * lengths[label] / average)
            score = sum(idf[token] * count * (k1 + 1) / (count + norm) for token, count in shared.items())
            scores[label] = score, matched_words(runs, shared, idf)
    return scores


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
