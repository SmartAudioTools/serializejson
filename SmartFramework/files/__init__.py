import os


def removeExistingPathAndCreateFolder(path):
    if os.path.exists(path):
        os.remove(path)
    folder = directory(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)


def cleanPath(path, endSlash=False):
    cleanedPath = path.replace("\\", "/").replace("//", "\\\\")
    if len(cleanedPath) > 0:
        if cleanedPath[-1] == "/":
            if not endSlash:
                cleanedPath = cleanedPath[:-1]
        else:
            if endSlash:
                cleanedPath = cleanedPath + "/"
    return cleanedPath


def directory(path):
    return cleanPath(os.path.dirname(path))


def joinPath(directory, name, ext=None):
    if directory:
        if name:
            string = cleanPath(directory, endSlash=True) + name
        else:
            string = cleanPath(directory)
    else:
        string = name
    if name and ext:
        string = string + "." + ext
    return string
