import string
from nltk.stem import WordNetLemmatizer
import nltk.tag

from definitions import *
from general_utils import increment_count, call_api


color_words = ["blue", "yellow", "black"]
shape_words = ["circle", "triangle", "square"]
integers = [str(i) for i in range(1,10)]
integer_words = "one two three four five six seven".split()
ALPHABET = "abcdefghijklmnopqrstuvwxyz"
MIN_COUNT = 5


def load_vocabulary(filename):
    vocab = set()
    with open(filename) as vocab_file:
        for line in vocab_file:
            word = line.rstrip()

            vocab.add(word)
    return vocab

def load_ngrams(filename, n):
    ngrams = {}
    with open(filename) as ngrams_file:
        for line in ngrams_file:
            tokens = line.rstrip().split()
            counts = int(tokens[-1])
            ngram = tuple(tokens[:-1]) if n > 1 else tokens[0]
            ngrams[ngram] = counts
    return ngrams


def write_ngrams(filename, ngrams):
    with open(filename, 'w') as ngrams_file:
        for ngram, count in sorted(ngrams.items(), key= lambda entry : entry[1], reverse=True):
            ngram = [ngram] if type(ngram)==str else ngram
            count = str(count)
            line = " ".join([t for t in ngram] + [count])
            ngrams_file.write(line + '\n')
    return

def load_synonyms(file_name):
    result = {}
    with open(file_name) as syns:
        for line in syns:
            line = line.rstrip()
            if len(line)>1:
                sep = line.find(' ')
                token = line[:sep]
                result[token] = eval(line[sep+1 :])
    return result



def get_ngrams_counts(dataset, max_ngram, include_start_and_stop = False):
    """
        Gets a collection of sentences and extracts ngrams up to size n.
        each sentence is a list of words.
    """

    all_ngrams = []
    for i in range(max_ngram):
        all_ngrams.append(dict())

    for sentence in dataset:

        for word in sentence:
            increment_count(all_ngrams[0], word)
        if include_start_and_stop:
            sentence = ["<s>"] + sentence; sentence.append("<\s>")
        length = len(sentence)
        for n in range(2, max_ngram+1):
            for i in range(n, length+1):
                increment_count(all_ngrams[n-1], tuple(sentence[i-n:i]))

    return all_ngrams


def clean_sentence(sent):
    '''
    
    :param sent: a string 
    :return: a copy of the original sentence, all in lower-case,
    without punctuation and without redundant whitespaces.  
    '''
    s = str.lower(sent).strip()

    if not s.isalnum():
        s = s.translate(s.maketrans("","", string.punctuation))
        s = " ".join(s.split())
    return s


def variants(word, alphabet = ALPHABET):
    """get all possible variants for a word
    borrowed from https://github.com/pirate/spellchecker
    """
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [a + b[1:] for a, b in splits if b]
    transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b)>1]
    replaces = [a + c + b[1:] for a, b in splits for c in alphabet if b]
    inserts = [a + c + b for a, b in splits for c in alphabet]
    return set(deletes + transposes + replaces + inserts), splits


def rank_suggestion(suggested_token, prev_token, next_token, unigram_counts, bigram_counts, p = 0.1):
       return p * unigram_counts.get(suggested_token, 0) + \
              ((1 - p) / 2) * bigram_counts.get((prev_token, suggested_token),0) + \
              ((1 - p) / 2) * bigram_counts.get((suggested_token, next_token),0)


def preprocess_sentences(sentences_dic, mode = None, processing_type= None):
    '''
    preprocesses the input sentences such that each returned sentences is a sequence of
    tokens that are part of the lexicon (???) seperated by whitespaces.
    using a hueristic approach for spell checking.

    :param sentences_dic: a dict[str, str] mapping from sentence identifier to sentence 
    :return: a dict[str, str] mapping from sentence identifier to sentence
    '''
    if processing_type is None:
        return sentences_dic
    if processing_type =='shallow':
        return {k : clean_sentence(s) for k,s in sentences_dic.items()}
    tokenized_sentences = {k : str.split(clean_sentence(s)) for k,s in sentences_dic.items()}
    unigrams, bigrams = get_ngrams_counts(tokenized_sentences.values(), 2)
    lemmatizer = WordNetLemmatizer()

    vocab = load_vocabulary(ENG_VOCAB_60K)
    # delete one-character-words except for 'a'
    for ch in ALPHABET[1:]:
        vocab.discard(ch)
    for er in ('ad','al','tow','bo','bow','lease','lest', 'thee', 'bellow'):
        vocab.discard(er) # very bad solution just for now @TODO
    # add digits
    for dig in range(10):
        vocab.add(str(dig))

    if mode=='r':
        unigrams_filtered = load_ngrams(TOKEN_COUNTS, 1)
        bigrams_filtered = load_ngrams(BIGRAM_COUNTS, 2)
    else:
        unigrams_filtered = {token : count for token, count in unigrams.items() if token in vocab}
        bigrams_filtered =  {bigram : count for bigram, count in bigrams.items() if
                             bigram[0] in unigrams_filtered and bigram[1] in unigrams_filtered}

    if mode == 'w':
        write_ngrams("tokens_counts.txt", unigrams_filtered)
        write_ngrams("bigrams_counts.txt", bigrams_filtered)

    # create an inventory of suggested corrections for invalid tokens from the sentences
    corrections_inventory = {}

    for unigram in unigrams:
        if unigram not in unigrams_filtered:
            unigram_variants, bigram_variants = variants(unigram)
            unigram_corrections = [v for v in unigram_variants if v in unigrams_filtered]
            bigram_corrections = [bi for bi in bigram_variants if bi in bigrams_filtered]
            corrections_inventory[unigram] = \
                (unigram_corrections, bigram_corrections[0] if len(bigram_corrections)>0 else None)

    tagging = {}

    for k, tok_sent in tokenized_sentences.items():
        for i,w in enumerate(tok_sent):
            if w in corrections_inventory: # otherwise it is a valid word
                unigram_suggestions, bigram_suggestion =  corrections_inventory.get(w, None)
                if bigram_suggestion is not None: # if a bigram suggestion exists use it
                    tok_sent[i] = " ".join(bigram_suggestion)
                elif len(unigram_suggestions) == 1:
                    tok_sent[i] = unigram_suggestions[0]
                elif len(unigram_suggestions) > 1: # if several suggestions exits, use the one with the highest ranking
                    prev_token = (tok_sent[i-1].split(" "))[-1] if i>0 else "<s>"
                    next_token = tok_sent[i+1] if i<len(tok_sent)-1 else "<\s>"
                    tok_sent[i] = max(unigram_suggestions, key = lambda token : \
                            rank_suggestion(token, prev_token, next_token, unigrams_filtered, bigrams_filtered))
                else:
                    #print("could not resolve token "+ w)
                    if unigrams[w]<10: # only in training
                        tok_sent[i] = "<UNK>"
                if w in vocab:
                    print ("{0}({1}): {2}".format(w, i, " ".join(tok_sent)))


    spellproofed_ss = {k : " ".join(s) for k,s in tokenized_sentences.items()}
    spellproofed_sentences = {k : s.split() for k,s in spellproofed_ss.items()}
    unigrams_checked, bigrams_checked = get_ngrams_counts(spellproofed_sentences.values(), 2)

    if mode == 'w':
        write_ngrams("tokens_spellproofed.txt", unigrams_checked)
        write_ngrams("bigrams_spellproofed.txt", bigrams_checked)

    for k, s in spellproofed_sentences.items():

        tagging[k] = nltk.pos_tag(s)
        for i, w in enumerate(s):
            pos = tagging[k][i][1]
            if pos.startswith('N'):
                lemma = lemmatizer.lemmatize(w, 'n')
            elif pos.startswith('V'):
                lemma = lemmatizer.lemmatize(w, 'v')
            else:
                lemma = w
            s[i] = lemma if s[i] not in ('is', 'are') else s[i]

    unigrams_lemmatized, bigrams_lemmatized = get_ngrams_counts(spellproofed_sentences.values(), 2)

    if mode == 'w':
        write_ngrams("tokens_lemmatized.txt", unigrams_lemmatized)
        write_ngrams("bigrams_lemmatized.txt", bigrams_lemmatized)


    return spellproofed_ss

    #@todo : handling also rare words (in training set) or unknown tokens (in test/validation)

def lemmatize_tokens(callapi=False):
    NOUN, VERB = 'n', 'v'
    tokens = load_ngrams(TOKEN_COUNTS, 1)
    word_lemmatizer = WordNetLemmatizer()
    d = {}
    for token, count in tokens.items():
        lemmas = []
        for pos in [NOUN, VERB]:
            lemmas.append((pos, word_lemmatizer.lemmatize(token, pos)))
        d[token] = (count, lemmas)

    for kvp in sorted(d.items(), key= lambda kvp : kvp[1][0], reverse=True):
        pass #print(kvp)

    all_word_forms = {}

    d_prime = {}
    for token,v in d.items():
        word_forms = set([token, v[1][0][1], v[1][1][1]])
        for w in word_forms:
            if w not in d_prime:
                d_prime[w] = set()
                d_prime[w].add(token)


    if callapi:
        for token, count in tokens.items():
            if count<20:
                word_forms = set([token, d[token][1][0][1], d[token][1][1][1]])
                for t in word_forms:
                    if t not in all_word_forms:
                        res = call_api(t)
                        if res is not None and "word" in res:
                            w = res["word"]
                            synonyms_n, synonyms_v, synonyms_other = [], [], []
                            for r in res.get("results", []):
                                if r["partOfSpeech"] == 'noun':
                                    for category in ("synonyms", "also", "similarTo", "derivative", "hasTypes", "typeOf"):
                                        synonyms_n.extend(r.get(category, []))
                                if r["partOfSpeech"] == 'verb':
                                    for category in ("synonyms", "also", "similarTo", "derivative", "hasTypes", "typeOf"):
                                        synonyms_v.extend(r.get(category, []))
                                else:
                                    for category in ("synonyms", "also", "similarTo", "derivative", "hasTypes", "typeOf"):
                                        synonyms_other.extend(r.get(category, []))

                            all_word_forms[w] = [synonyms_n, synonyms_v, synonyms_other]
        for k,v in all_word_forms.items():
            print(k,v)
        time.sleep(5)
    else:
        all_word_forms = load_synonyms(SYNONYMS)

    bigrams = load_ngrams(BIGRAM_COUNTS, 2)
    suggestions_synonyms = {}
    for k,v in all_word_forms.items():
        if k in integers or k in integer_words:
            continue
        suggestions_synonyms[k] = [[], [], []]
        for i in range(3):
            for w in v[i]:
                suggestions_synonyms[k][i].extend(d_prime[w]  if w in d_prime else [])
                if bigrams.get(tuple(w.split()) , 0) > 3:
                    suggestions_synonyms[k][i].append(w)

    print("#########################################")
    #for k,v in suggestions_synonyms.items():
     #   print(k,v)
    return suggestions_synonyms

    #
    # for token, count in tokens.items():
    #     if count < 20:
    #         word_forms = set([token, d[token][1][0][1], d[token][1][1][1]])
    #         for t in word_forms:
    #             print(t)

def replace_rare_words(tok_sent, unigrams,bigrams, suggestions):
    tagging = nltk.pos_tag(tok_sent)
    lemmatizer = WordNetLemmatizer()
    for i,w in enumerate(tok_sent):
        if str.isdigit(w):
            continue
        if unigrams.get(w,0) <=5:
            pos = tagging[i][1][0]
            if pos == 'N':
                lemma = lemmatizer.lemmatize(w, 'n')
                idx=0
            elif pos == 'V':
                lemma = lemmatizer.lemmatize(w, 'v')
                idx=1
            else:
                lemma = w
                idx=2
            options = suggestions[lemma][idx] if lemma in suggestions else []
            options.extend([lemma, w])
            if len(options) == 1:
                res = options[0]
            elif len(options) > 1:  # if several suggestions exits, use the one with the highest ranking
                prev_token = (tok_sent[i - 1].split(" "))[-1] if i > 0 else "<s>"
                next_token = tok_sent[i + 1] if i < len(tok_sent) - 1 else "<\s>"
                res = max(options, key=lambda token: \
                    rank_suggestion(token, prev_token, next_token, unigrams, bigrams))
            if tok_sent[i] != res:
                print (" ".join(tok_sent))
                tok_sent[i] = res
                print(" ".join(tok_sent))
                print("%%%%%%%%%%%%%%%%%%%%%%%%%")


    return



def formalize_sentence(s):
    s = [w for w in s.split()]

    forms = [(integers, [], 'n'), (shape_words, [], 's'), (color_words, [], 'c')]

    for i,w in enumerate(s):
        # remove plural and convert integer words:
        if w.endswith('s') and w[:-1] in shape_words:
            s[i] = w[:-1]
        if w in integer_words:
            s[i] = integers[integer_words.index(s[i])]
    return s

def further_process_sentences(sentences):
    all_word_forms = load_synonyms(SYNONYMS)
    unigrams = load_ngrams(TOKEN_COUNTS,1 )
    bigrams = load_ngrams(BIGRAM_COUNTS, 2)
    for k,s in sentences.items():
        s = formalize_sentence(s)
        replace_rare_words(s, unigrams, bigrams, all_word_forms )
    return


if __name__ == '__main__':
    #lemmatize_tokens(callapi=True)
    #data, sentences = build_data(read_data(TRAIN_JSON))
    #preprocess_sentences(sentences, processing_type='thorough')
    print()


