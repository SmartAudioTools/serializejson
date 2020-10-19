# -*- coding: utf-8 -*-
"""
Created on Sun Oct 18 10:05:09 2020

@author: Baptiste
"""

import serializejson

object1 = set([1, 2])
object2 = set([3, 4])
dumped1 = serializejson.dumps(object1)
print(dumped1)
loaded1 = serializejson.loads(dumped1)
serializejson.dump(object2, "dumped2.json")
loaded2 = serializejson.load("dumped2.json")
