from .log import log


# with INIT -----------------
class C_single_line:
    def __init__(self, attribut_1=1, attribut_2 = 2):
        self.attribut_1 = attribut_1
        self.attribut_2 = attribut_2
        self.int_list = [1,2,3]
        self.int_tuple =(4,5,6)
        self.float_list = [1.,2.,3.]
        self.float_tuple =(4.,5.,6.)
  
    def __reduce__(self):
        return (type(self), (self.attribut_1,self.attribut_2), self.__dict__)