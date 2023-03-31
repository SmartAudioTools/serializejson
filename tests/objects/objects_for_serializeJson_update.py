leaf_num = 0


class Root:
    def __init__(self):
        self.branch1 = Branch()
        self.branch2 = Branch()


class Branch:
    def __init__(self):
        self.leafs = [Leaf(), Leaf()]


class Leaf:
    def __init__(self):
        global leaf_num
        leaf_num += 1
        self.value = leaf_num
