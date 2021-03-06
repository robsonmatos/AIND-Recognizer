import math
import statistics
import warnings

import numpy as np
from hmmlearn.hmm import GaussianHMM
from sklearn.model_selection import KFold
from asl_utils import combine_sequences
from operator import itemgetter


class ModelSelector(object):
    """
    base class for model selection (strategy design pattern)
    """

    def __init__(self, all_word_sequences: dict, all_word_Xlengths: dict, this_word: str, n_constant=3,
                 min_n_components=2, max_n_components=10, random_state=14, verbose=False):
        self.words = all_word_sequences
        self.hwords = all_word_Xlengths
        self.sequences = all_word_sequences[this_word]
        self.X, self.lengths = all_word_Xlengths[this_word]
        self.this_word = this_word
        self.n_constant = n_constant
        self.min_n_components = min_n_components
        self.max_n_components = max_n_components
        self.random_state = random_state
        self.verbose = verbose

    def select(self):
        raise NotImplementedError

    def base_model(self, num_states):
        # with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        # warnings.filterwarnings("ignore", category=RuntimeWarning)
        try:
            hmm_model = GaussianHMM(n_components=num_states, covariance_type="diag", n_iter=1000,
                                    random_state=self.random_state, verbose=False).fit(self.X, self.lengths)
            if self.verbose:
                print("model created for {} with {} states".format(self.this_word, num_states))
            return hmm_model
        except:
            if self.verbose:
                print("failure on {} with {} states".format(self.this_word, num_states))
            return None


class SelectorConstant(ModelSelector):
    """ select the model with value self.n_constant

    """

    def select(self):
        """ select based on n_constant value

        :return: GaussianHMM object
        """
        best_num_components = self.n_constant
        return self.base_model(best_num_components)


class SelectorBIC(ModelSelector):
    """ select the model with the lowest Baysian Information Criterion(BIC) score

    http://www2.imm.dtu.dk/courses/02433/doc/ch6_slides.pdf
    Bayesian information criteria: BIC = -2 * logL + p * logN
    """

    def select(self):
        """ select the best model for self.this_word based on
        BIC score for n between self.min_n_components and self.max_n_components

        :return: GaussianHMM object
        """
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        results = []

        for num_states in range(self.min_n_components, self.max_n_components + 1):
            if self.verbose:
                print("Word: {}, Number of sequences: {}, Number of states: {}".format(self.this_word,
                                                                                       len(self.sequences), num_states))
            try:
                model = self.base_model(num_states)
                score = self.score(num_states, model)
                is_valid = True
                if self.verbose:
                    print(" - Score using {} states: {}".format(num_states, score))

            except:
                is_valid = False
                if self.verbose:
                    print(" - Failed to train model using {} states".format(num_states))

            if is_valid:
                results.append((model, score))

        # Find the model that minimizes the score (BIC)
        return min(results, key=itemgetter(1))[0]

    def score(self, num_states, model):

        # Determine number of features
        num_features = len(self.X[0])

        # Determine number of parameters
        num_param = num_states**2 + 2*num_features*num_states - 1

        return -2*model.score(self.X, self.lengths) + num_param*np.log(len(self.X))


class SelectorDIC(ModelSelector):
    """ select best model based on Discriminative Information Criterion

    Biem, Alain. "A model selection criterion for classification: Application to hmm topology optimization."
    Document Analysis and Recognition, 2003. Proceedings. Seventh International Conference on. IEEE, 2003.
    http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.58.6208&rep=rep1&type=pdf
    DIC = log(P(X(i)) - 1/(M-1)SUM(log(P(X(all but i))
    """

    def select(self):
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        results = []

        for num_states in range(self.min_n_components, self.max_n_components + 1):

            if self.verbose:
                print("Word: {}, Number of sequences: {}, Number of states: {}".format(self.this_word,
                                                                                       len(self.sequences), num_states))
            model = self.base_model(num_states)
            score = self.score(model)

            if self.verbose:
                print(" - Score using {} states: {}".format(num_states, score))

            if score:
                results.append((model, score))

        # Find the model that minimizes the score (BIC)
        return max(results, key=itemgetter(1))[0]

    def score(self, model):

        anti_evidences = []

        for X, lengths in [self.hwords[word] for word in self.words if self.this_word != word]:

            try:
                anti_evidences.append(model.score(X, lengths))
            except:
                continue

        try:
            evidence = model.score(self.X, self.lengths)
        except:
            return None

        return evidence - np.mean(anti_evidences)


class SelectorCV(ModelSelector):
    """ select best model based on average log Likelihood of cross-validation folds

    """

    def select(self):
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        num_splits = 3
        results = []

        for num_states in range(self.min_n_components, self.max_n_components+1):

            cv_scores = []

            if self.verbose:
                print("Word: {}, Number of sequences: {}, Number of states: {}".format(self.this_word,
                                                                                       len(self.sequences), num_states))

            if len(self.sequences) < num_splits:
                split_method = KFold(n_splits=len(self.sequences))
            else:
                split_method = KFold(n_splits=num_splits)

            for cv_train_idx, cv_test_idx in split_method.split(self.sequences):

                try:
                    self.X, self.lengths = combine_sequences(cv_train_idx, self.sequences)
                    model = self.base_model(num_states)
                    self.X, self.lengths = combine_sequences(cv_test_idx, self.sequences)
                    score = model.score(self.X, self.lengths)
                    cv_scores.append(score)

                    if self.verbose:
                        print(" - Score using {} states: {}".format(num_states, score))

                except:
                    if self.verbose:
                        print(" - Failed to train model using {} states".format(num_states))

            if len(cv_scores):
                avg_score = np.mean(cv_scores)
                results.append((num_states, avg_score))
                if self.verbose:
                    print(" - Average score: {}".format(avg_score))

        # Find number of components which maximizes the log likelihood
        best_num_components = max(results, key=itemgetter(1))[0]

        if self.verbose:
            print(" - Best model found: {} states".format(best_num_components), end=' [')
            print(*results, sep=', ', end=']\n')

        # Generate the model for the best number of components
        self.X, self.lengths = self.hwords[self.this_word]

        return self.base_model(best_num_components)
