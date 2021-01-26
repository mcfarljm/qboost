#    Copyright 2018 D-Wave Systems Inc.

#    Licensed under the Apache License, Version 2.0 (the "License")
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at

#        http: // www.apache.org/licenses/LICENSE-2.0

#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.


from __future__ import print_function, division

import sys

import numpy as np

from sklearn import preprocessing, metrics
from sklearn.ensemble import AdaBoostClassifier
from sklearn.datasets import load_breast_cancer, fetch_openml
from sklearn.impute import SimpleImputer
from dwave.system.samplers import DWaveSampler
from dwave.system.composites import EmbeddingComposite

from qboost import WeakClassifiers, QBoostClassifier, QboostPlus


def metric(y, y_pred):

    return metrics.accuracy_score(y, y_pred)


def train_models(X_train, y_train, X_test, y_test, lmd, verbose=False):
    """
    Train a series of 4 boosted classification models.
    
    Args:
        X_train (array):
            2D array of features for training.
        y_train (array):
            1D array of labels for training.
        X_test (array):
            2D array of features for testing.
        y_test (array):
            1D array of labels for testing.
        lam (float):
            lambda parameter to control regularization term.
        verbose (bool):
            If True, print weak classifier weights.
    """
    NUM_READS = 3000
    NUM_WEAK_CLASSIFIERS = 35
    # lmd = 0.5
    TREE_DEPTH = 3

    # define sampler
    dwave_sampler = DWaveSampler()
    emb_sampler = EmbeddingComposite(dwave_sampler)

    N_train = len(X_train)
    N_test = len(X_test)

    print('Size of training set:', N_train)
    print('Size of test set:    ', N_test)
    print('Number of weak classifiers:', NUM_WEAK_CLASSIFIERS)
    print('Tree depth:', TREE_DEPTH)


    # input: dataset X and labels y (in {+1, -1}

    # Preprocessing data
    # imputer = SimpleImputer()
    scaler = preprocessing.StandardScaler()     # standardize features
    normalizer = preprocessing.Normalizer()     # normalize samples

    # X = imputer.fit_transform(X)
    X_train = scaler.fit_transform(X_train)
    X_train = normalizer.fit_transform(X_train)

    # X_test = imputer.fit_transform(X_test)
    X_test = scaler.fit_transform(X_test)
    X_test = normalizer.fit_transform(X_test)

    ## Adaboost
    print('\nAdaboost:')

    clf = AdaBoostClassifier(n_estimators=NUM_WEAK_CLASSIFIERS)

    # scores = cross_val_score(clf, X, y, cv=5, scoring='accuracy')
    clf.fit(X_train, y_train)

    hypotheses_ada = clf.estimators_
    # clf.estimator_weights_ = np.random.uniform(0,1,size=NUM_WEAK_CLASSIFIERS)
    y_train_pred = clf.predict(X_train)
    y_test_pred = clf.predict(X_test)

    print('Accuracy on training set: {:5.2f}'.format(metric(y_train, y_train_pred)))
    print('Accuracy on test set:     {:5.2f}'.format(metric(y_test, y_test_pred)))

    # Ensembles of Decision Tree
    print('\nDecision tree:')

    clf2 = WeakClassifiers(n_estimators=NUM_WEAK_CLASSIFIERS, max_depth=TREE_DEPTH)
    clf2.fit(X_train, y_train)

    y_train_pred2 = clf2.predict(X_train)
    y_test_pred2 = clf2.predict(X_test)

    if verbose:
        print('weights:\n', clf2.estimator_weights)

    print('Accuracy on training set: {:5.2f}'.format(metric(y_train, y_train_pred2)))
    print('Accuracy on test set:     {:5.2f}'.format(metric(y_test, y_test_pred2)))

    # Ensembles of Decision Tree
    print('\nQBoost:')

    DW_PARAMS = {'num_reads': NUM_READS,
                 'auto_scale': True,
                 # "answer_mode": "histogram",
                 'num_spin_reversal_transforms': 10,
                 # 'annealing_time': 10,
                 }

    clf3 = QBoostClassifier(n_estimators=NUM_WEAK_CLASSIFIERS, max_depth=TREE_DEPTH)
    clf3.fit(X_train, y_train, emb_sampler, lmd=lmd, **DW_PARAMS)

    y_train_dw = clf3.predict(X_train)
    y_test_dw = clf3.predict(X_test)

    if verbose:
        print('weights\n', clf3.estimator_weights)

    print('Accuracy on training set: {:5.2f}'.format(metric(y_train, y_train_dw)))
    print('Accuracy on test set:     {:5.2f}'.format(metric(y_test, y_test_dw)))


    # Ensembles of Decision Tree
    print('\nQBoostPlus:')
    clf4 = QboostPlus([clf, clf2, clf3])
    clf4.fit(X_train, y_train, emb_sampler, lmd=lmd, **DW_PARAMS)
    y_train4 = clf4.predict(X_train)
    y_test4 = clf4.predict(X_test)

    if verbose:
        print('weights\n', clf4.estimator_weights)

    print('Accuracy on training set: {:5.2f}'.format(metric(y_train, y_train4)))
    print('Accuracy on test set:     {:5.2f}'.format(metric(y_test, y_test4)))


    print()
    print('=' * 28)
    print("{:14}{:7}{:7}".format("Method", "Train", "Test"))
    print('-' * 28)
    for name, _y_train_pred, _y_test_pred in zip(["Adaboost", "DecisionTree", "Qboost", "QboostIt"],
                                                 [y_train_pred, y_train_pred2, y_train_dw, y_train4],
                                                 [y_test_pred, y_test_pred2, y_test_dw, y_test4]):
        print("{:14}{:<7.2f}{:<7.2f}".format(name, metric(y_train, _y_train_pred), metric(y_test, _y_test_pred)))
    print('=' * 28)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["mnist", "wisc"], help="data set to analyze")

    args = parser.parse_args()

    if args.dataset == 'mnist':

        print('MNIST handwritten digits data set:')

        mnist = fetch_openml('mnist_784', version=1)

        idx = np.arange(len(mnist['data']))
        np.random.shuffle(idx)

        n = 5000
        idx = idx[:n]
        idx_train = idx[:2*n//3]
        idx_test = idx[2*n//3:]

        X_train = mnist['data'][idx_train]
        X_test = mnist['data'][idx_test]

        # Note: mnist['target'] is an array of string numbers, hence the comparison with '4'
        y_train = 2*(mnist['target'][idx_train] <= '4') - 1
        y_test = 2*(mnist['target'][idx_test] <= '4') - 1

        train_models(X_train, y_train, X_test, y_test, 1.0)

    elif args.dataset == 'wisc':

        print('Wisconsin breast cancer data set:')

        wisc = load_breast_cancer()

        idx = np.arange(len(wisc.target))
        np.random.shuffle(idx)

        # train on a random 2/3 and test on the remaining 1/3
        idx_train = idx[:2*len(idx)//3]
        idx_test = idx[2*len(idx)//3:]

        X_train = wisc.data[idx_train]
        X_test = wisc.data[idx_test]

        y_train = 2 * wisc.target[idx_train] - 1  # binary -> spin
        y_test = 2 * wisc.target[idx_test] - 1

        train_models(X_train, y_train, X_test, y_test, 1.0)
