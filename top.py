from hw_config import hwc
from hw_config import Config
import math as m
import torch
from inst_stack import inst_stack
import os
from compiler4in1 import Compile

config = Config(al=128, pc=16, scr=4, bus_width=128, is_depth=2, os_depth=1024)
acc0 = hwc(config)
gli = ['mvm', (32, 256, 2)]
data_stream = 'wspp'
VERIFY = 0

compile_result = Compile(config, gli, data_stream, VERIFY)
