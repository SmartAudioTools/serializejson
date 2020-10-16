# -*- coding: utf-8 -*-

'''
import sip
API_NAMES = ["QDate", , "QString", "QTextStream", "QTime", "QUrl", "QVariant"]
API_VERSION = 2
for name in API_NAMES:
    sip.setapi(name, API_VERSION)


#------- Imports Bibliotheque Tierces ------------

import sys
import timer 
import numpy
from   qtpy import QtCore, QtGui,uic
import os.path

#------- Imports Bibliotheque SmartFramework ------------
import audio
import events
import ui
import video
import par
#import tools
import designer
import midi
#------------------
'''
from pybase64 import b64decode
from numpy import frombuffer,unpackbits,uint8,ndarray,int32,int64
from numpy import dtype as numpy_dtype
from SmartFramework.serialize import serializeParameters
import sys

#defaultIntType =  numpy_dtype("int_")
nb_bits = sys.maxsize.bit_length()+1

def bytearrayB64(b64):
    return bytearray(b64decode(b64,validate=True))

def bytesB64(b64):
    return b64decode(b64,validate=True) 
            
def numpyB64(str64,dtype = None,shapeOrLen = None):
    decodedBytes = b64decode(str64,validate=True)    # str64 -> bytes : decodage avec copie 
    if dtype in ("bool",bool) : 
        uintContaining8bits = frombuffer(decodedBytes,uint8)    # pas de copie ?
        uintContaining1bit  = unpackbits(uintContaining8bits) # copie
        if shapeOrLen is None : 
            return uintContaining1bit 
        else : 
            return ndarray(shapeOrLen,dtype,uintContaining1bit)      # a priori pas de recopie
    else : 
        if isinstance(dtype,list):
            dtype = [(str(champName),champType) for champName,champType in dtype]
        if shapeOrLen is None :
            #return nympy.frombuffer(decodedBytes)
            array = frombuffer(decodedBytes,dtype) # evite de faire une recopie 
        else :
            array = ndarray(shapeOrLen,dtype,decodedBytes) # evite de faire une recopie  ? a priori oui
        array.flags.writeable = True
        
        if nb_bits == 32 and serializeParameters.numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit : # pour pouvoir deserialiser les classifiers en python 32 bit ?
            if array.dtype in (int64, 'int64'):
                array = array.astype(int32)
            elif isinstance(dtype,list):
                newTypes = []
                for champ  in dtype :
                    champName,champType = champ
                    if champName  : 
                        champType = numpy_dtype(champType)
                        if champType in (int64, 'int64'):
                            newTypes.append((champName,int32))
                        else : 
                            newTypes.append((champName,champType)) 
                newDtype = numpy_dtype(newTypes,align = True)
                newN =  ndarray(len(array),newDtype) 
                for champName,champType in newTypes : 
                    if champName:
                        newN[champName][:] = array[champName]
                array = newN
        return array   
            #return numpy.ndarray(shape,dtype,bytearray(decodedBytes)) # obligé de mettre bytearray? sinon le tableau sera immutable , et si on force à l'etre avec flags.readonly = False on va changer la chaine de caractère sous jacent et potientiellement foutre la merde sur dictionnaire qui ont la meme clef?
        
    # str -> bytearray : copie ? 
    # bytearray -> nympy : pas de copie 
    #a.flags.writable = True # a priori dangereux , car va pouvoir modifier valeur d'une string... qui est sencé etre imutable .
fromB64 = numpyB64 # pour pouvoir ouvrir d'anciens fichiers serializés