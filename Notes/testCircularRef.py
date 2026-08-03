# -*- coding: utf-8 -*-
import pickle
"""
Created on Sat May 30 11:10:47 2015

@author: Baptiste
"""

# from tinydb import TinyDB, where
# import os

# class MaClasse():
# def __init__(self,value):
#        self.value = value


# monInstance = MaClasse(10)

A = {"name": "A"}
B = {"name": "B"}
A["link"] = B
B["link"] = A
print(A)

s = pickle.dumps(A)
newA = pickle.loads(s)
print(newA)
# print newA == A
# Tiny DB
"""
db = TinyDB('db.json')
db.insert({'int': 1, 'char': 'a'})
table = db.table('name')
table.insert({'monInstance': A})
#os.system("pause")"""
