# -*- coding: utf-8 -*-
"""
Created on Sun Oct 18 10:05:09 2020

@author: Baptiste
"""

import serializejson

# serialize in string
object1 = set([1, 2])
dumped1 = serializejson.dumps(object1)
loaded1 = serializejson.loads(dumped1)
print(dumped1)

# serialize in file
object2 = set([3, 4])
serializejson.dump(object2, "dumped2.json")
loaded2 = serializejson.load("dumped2.json")
print(open("dumped2.json").read())
