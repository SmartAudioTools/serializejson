# serialisation de tableaux numpy -------------

# numpy_array_dumped_base64  = True     # dit si doit utiliser l'encodage en base64 pour l'encodage de tableau numpy. Ce paramètre n'est modifiable que directement ici.
# numpy_array_readable_max_size = 0    # force tout de même à  encoder les tableaux de taille <= numpy_array_readable_max_size, sous forme de liste lisible même si on utilise numpy_array_dumped_base64 = True ( et donc d'utiliser numpy.array au lieu du construcuteur partir de bytes comme numpy.ndarray (pour tableau de dim > 2 si use_numpyB64 == False ), numpyB64 ou autre), paramètre directement ici , ou en paramètre de SerializeInterface et SerializePresetUI

# a regrouper sous un seul parametre determine dependance à SmartFramework
# use_numpyB64_bytearrayB64 = True
# use_numpyB64        = True # précise si on doit utiliser mon constructeur SmartFramework.numpyB64() pour les tableau rendant alors le json dependant de ma bibliotheque ou utiliser une syntaxe plus complexe mais où numpy suffit .  l'avantagede numpyB64 est d'etre beaucoup plus compact.
# use_bytearrayB64    = True     # précise si on doit utiliser mon constructeur SmartFramework.bytearrayB64() pour les bytearray rendant alors le json dependant de ma bibliotheque ou bytearray(base64.b64decode(..))  . l'avantage de bytearrayB64 est d'etre beaucoup plus compact et de déclancher une erreure si y'a un caracter qui est pas dans la base .
# use_bytesB64        = True	    # précise si on doit utiliser mon constructeur SmartFramework.bytesB64() pour les bytes rendant alors le json dependant de ma bibliotheque ou base64.b64decode . l'avantage de bytesB64 est d'utilsier pyBase64 beaucoup plus rapide que base64 et de déclancher une erreure si y'a un caracter qui est pas dans la base .

# a laisser là  on y toucher à priori pas -----------------------

# base64_for_bytes = True  # dit si doit utiliser l'encodage en base64 pour l'encodage des bytes et bytes array, si pas ascii printables. Ce paramètre n'est modifiable que directement ici. Attention s'il est mis à False, si serialize en json plantera sur les bytes avec des valeures < 128 dans tuple_from_bytes => le laisser toujours True ?
strict_pickle = False
do_checks = True
numpyB64_convert_int64_to_int32_and_align_in_Python_32Bit = True  # dis si numpyB64 doit deserialiser les tableau int64 en int32 quand utilise python 32 bits (pour prendre moins de place? ou pour pouvoir deserialiser les classifiers en python 32 bit ?

# noms de fichiers ----------------------------
forceRelativePath = False  # force noms de fichier en chemin relatif ,utilisé que dans serializeRepr.py dans la fonction reprFile et en plus mal codé. Ce paramètre n'est modifiable que directement ici
forceAbsolutPath = False  # force noms de fichier en chemin absolut ,utilisé que dans serializeRepr.py dans la fonction reprFile. Ce paramètre n'est modifiable que directemen ici

# serialisation des objets -----------------------------------------
# attributes_filter   = "_"        #  dit si doit filtrer les attribute commencant par la chaine stocke dans filtre.
# call_setters      = True       # dit si doit tenter d'appeler setter pour la restauration des attributes.
# False :  		    + conforme au comportement de pickle (si on n'utiliser pas de filtre "_")
# True  :  		    + permet d'effectuer des traitements, de mettre en place des choses (par ex interface I/O) ,
#             	    +  permet de rafraichir UI
#             	    - risque de déclancher réaction en chaine en sortant signal ? (si le setter envoie signal)
#             	    - pas meme comportement que pickle
#
# pickle  : 		True : INCOMPATIBLE PICKLE, pickle par defaut ne fera jamais appele au setter. Il faut coder __setstate__ pour le faire
# serializePython: True : appel en dur de setattribute à la serialisation 	  / False :  le fera de toute facon si c'est une propriétée...=> INCOMPATIBLE PICKLE
# serializejson : 	True : appel dynamique de setattribute à la deserialisation / False : pas d'appel du setter
# serialiseRepr :	A REVOIR ET TESTER

# uniquement pour serializePython et serializeRepr ----------------------------------
# make_imports       = True       # dit si doit rajouter ligner d'imports au debut du fichier serialisé.
# space              = False      # dit si met des espace lors de la serialisation avec serializePython et serializeRepr pour les iterable (liste, tuple), les dictionnaire et les objets (False permet de conserver de la memoire et donc d'eviter de planter si gros fichier, mais mois lisible)
# tabulation         = '\t'       # tabulation utilisée, peut êter " ", "  ", "    ", "\t" . On utilisara de préférence "\t" pour economiser de la mémoire tout en restant lisible
# round_float         = 0          # 0 si pas d'arrondi , entier correspondant au nombre de chiffres après la virgule sinon (permet de preserver mémoire et  eviter plantage de python)
# numpy_types_to_python_types = True # ne sert que pour la serialisation en python !?
