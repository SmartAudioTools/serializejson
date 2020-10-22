# -*- coding: utf-8 -*-
def sort_dict(d):
    return {key: d[key] for key in sorted(d)}


def updateWithoutOverwrite(d1, d2):
    for key in d2.keys() - d1.keys():
        d1[key] = d2[key]


def reverseDict(D):
    revD = dict()
    for key, value in D.items():
        revD[value] = key
    return revD


def remove(dictionnaire, toRemove=None):
    for key in dictionnaire.keys():
        if key == toRemove:
            # dectecte un attribut a cacher => recopie le dictionnaire sans prendre les attributs commencant pas '_'
            dict2 = dict()
            for key, value in dictionnaire.items():
                if key != toRemove:
                    dict2[key] = value
            return dict2
    return dictionnaire


def filtered(dictionnaire, filterChar="_"):
    for key in dictionnaire:
        if key[0] == filterChar:
            # dectecte un attribut a cacher => recopie le dictionnaire sans prendre les attributs commencant pas '_'
            dict2 = dict()
            for key, value in dictionnaire.items():
                if key[0] != filterChar:
                    dict2[key] = value
            return dict2
    return dictionnaire


def removeDict(jsonDict, communDict):
    for key, value in communDict.items():
        if type(value) is dict:
            removeDict(jsonDict[key], value)
            if not jsonDict[key]:
                del jsonDict[key]
        else:
            del jsonDict[key]


noCommun = {}


def findCommun(elts):
    # compare les dictionnaires
    if type(elts[0]) == dict:
        setKeys = [set(elt.keys()) for elt in elts]
        communKeys = setKeys[0]
        for setKey in setKeys:
            communKeys = communKeys.intersection(setKey)
        baseDict = dict()
        for key in communKeys:
            values = [elt[key] for elt in elts]
            valueBase = findCommun(values)
            if valueBase is not noCommun:
                baseDict[key] = valueBase
        if not baseDict:
            baseDict = noCommun
        return baseDict

    # compare tous les elements au premier

    elt0 = elts[0]
    for elt in elts:
        if type(elt) is not type(elt0):
            return noCommun
        elif str(type(elt0)) == "<type 'numpy.ndarray'>":
            if len(elt0) != len(elt) or not (elt0 == elt).any():
                return noCommun
        elif elt0 != elt:
            return noCommun
    return elt0


def removeAndReturnCommun(elts):
    communDict = findCommun(elts)
    for elt in elts:
        removeDict(elt, communDict)
    return communDict


def addChamps(d, champs):
    dicts = [d[champ] for champ in champs]
    return addDicts(dicts)


def addDicts(dicts):
    result = dict()
    for d in dicts:
        for key, value in d.items():
            if key in result:
                if type(value) is dict:
                    result[key] = addDicts([value, result[key]])
                else:
                    raise Exception("la clef %s existe deja" % key)
            else:
                result[key] = value

    return result
