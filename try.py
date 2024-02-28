from hw_config import hwc
from hw_config import Config
import math as m
import torch

a = torch.randint(-128, 127,size=(1, 1),dtype=torch.int8)
print(a)

b = a.to(dtype=torch.int32)

print(b)

c = b * pow(2,2)

print(c)