import hw_config as cfg
import math as m
import torch
from inst_stack import inst_stack
import os
from compiler import MicroInstructionCompiler

hw_cfg = cfg.Config(al=128, pc=16, scr=16, bus_width=128, is_depth=1024, os_depth=1024)
acc0 = cfg.hwc(config= hw_cfg)

workload = ['mvm', (512, 2048, 1024)]
dataflow = 'wspp'
cf_compiler = MicroInstructionCompiler(hw_cfg, workload, dataflow, VERIFY=False)
cf_compiler.compile()
cf_compiler.print()

# Additional code to output or work with the compiled instructions
