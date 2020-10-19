# -*- coding: utf-8 -*-
"""
Created on Mon Oct 19 09:45:21 2020

@author: Baptiste
"""
"""
import serializejson 
object1 = set([1,2])
object2 = set([3,4])
dumped1 = serializejson.dumps(object1)
print(f"id {id(object2)} :  {object2}")
serializejson.loads(dumped1,obj = object2, updatables_classes = [set])
print(f"id {id(object2)} :  {object2}")
"""
"""
import serializejson 
object1 = bytes(range(255))
dumped1 = serializejson.dumps(object1)
print(serializejson.loads(dumped1))
"""
"""
import serializejson 
encoder = serializejson.Encoder()
for elt in range(10):
    encoder.append(elt,"my_list.json")
print(serializejson.load("my_list.json"))
"""
import serializejson

encoder = serializejson.Encoder("my_list.json")
for elt in range(1):
    encoder.append(elt)
for elt in serializejson.Decoder("my_list.json"):
    print(elt)
