"""Catalogue d'objets du dépôt, partagé par `test_serialize_vs_pickle` et le banc.

`catalogue()` fusionne `basic_objects` (catégories de types python) et les modules de classes
(`init_*`, `no_init*`, `new_getnewargs`…) : un module qui expose `objects` y verse ses
catégories, les autres deviennent la catégorie `object_<module>`, une instance par classe `C_…`.
Avant le 02/10/2026 cette fusion vivait dans le test seul, et le banc ne voyait que
`basic_objects` : aucune des voies de construction (arguments, slots, setters, getstate…)
n'avait de barre.
"""
import importlib
import inspect

MODULES = [
    "new_getnewargs",
    "init_arg",
    "init_args_explicite_getstate",
    "init_args_filtered_state_explicite_getstate",
    "init_args_filtered_state",
    "init_args_ghost_getinitargs",
    "init_args",
    "init_default_explicite_getstate",
    "init_default_filtered_state_explicite_getstate",
    "init_default_filtered_state",
    "init_default_ghost_getinitargs",
    "init_default_ghots_getstate",
    "init_default",
    "init_kwarg",
    "init_kwargs_explicite_getstate",
    "init_kwargs_filtered_state_explicite_getstate",
    "init_kwargs_filtered_state",
    "init_kwargs",
    "no_init",
    "no_init_filtered_state",
    "no_init_slots",
    "no_init_slots_and_dict",
    "no_init_slots_subclass",
    "no_init_setters",
    "getstate_no_string_keys",
    "dict_subclasses",
    "tuple_subclasses",
    "properties",
    "init_and_new",
    "single_line",
]


def _module(nom):
    return importlib.import_module("." + nom, __name__)


def catalogue(pyqt5=False, numpy=False):
    """Rend `(objects, authorized_classes)` : {catégorie: {clé: objet}} et les classes à
    autoriser pour relire le tout. Le dict rendu est neuf (`basic_objects.objects` n'est pas
    modifié) ; les objets, eux, sont ceux des modules."""
    objects = dict(_module("basic_objects").objects)
    modules = [_module(nom) for nom in MODULES]
    if pyqt5:
        from PyQt5 import QtWidgets
        global _application  # pyqt_objects crée des widgets dès l'import
        _application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        modules.append(_module("pyqt_objects"))
    if numpy:
        objects.update(_module("numpy_objects").objects)
    authorized_classes = []
    for module in modules:
        authorized_classes.extend(getattr(module, "authorized_classes", ()))
        if hasattr(module, "objects"):
            objects.update(module.objects)
            for categorie in module.objects.values():
                for obj in categorie.values():
                    authorized_classes.append(obj if inspect.isclass(obj) else type(obj))
        else:
            objects["object_" + module.__name__] = categorie = {}
            for nom, classe in vars(module).items():
                if nom.startswith("C_"):
                    categorie[nom] = classe()
                    authorized_classes.append(classe)
    return objects, authorized_classes
