'''
Created on Jul 31, 2015

@author: dhadka
'''

import numpy as np

def convert_to_numpy(output, field, index=0):
    if len(output) == 0:
        return np.empty([0])
    
    result = np.empty([len(output)])
    
    for i, map in enumerate(output):
        value = map[field]
        
        if type(value) is list:
            result[i] = value[index]
        else:
            result[i] = value
        
    return result

class SALibSamples(object):
    '''
    Iterable that convert SALib's inputs, including
        1) The problem map with a field called "names" containing the parameter names, and
        2) The samples generated by SALib
    into a map usable by Executioner.
    '''
    
    def __init__(self, names, values):
        super(SALibSamples, self).__init__()
        self.index = -1
        self.names = names["names"] if type(names) is dict else names
        self.values = values
        
    def __iter__(self):
        return self
    
    def __next__(self):
        return self.next()
    
    def next(self):
        if self.index >= len(self.values)-1:
            raise StopIteration
        else:
            self.index = self.index + 1
            result = {}
            
            for i in range(len(self.names)):
                result[self.names[i]] = self.values[self.index][i]
                
            return result
        