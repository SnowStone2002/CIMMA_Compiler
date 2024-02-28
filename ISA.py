# ISA format

# total length: 43

# all possible variables:

# op_code [2:0]
# fd_ar   [8:0]     IS中的addr
# cm_ar   [9:0]     CIM的addr
# ca      [3:0]     CIM的local switch打到哪个
# gd_wten
# gd_rden
# acc_en
# addr_rd [8:0]
# addr_wt [8:0]
# oob_wtp [2:0]
# oob_rdp [2:0]

from hw_config import hwc
from hw_config import Config
config = Config(al=128, pc=16, scr=16, is_depth=512, os_depth=1024)
acc0 = hwc(config)

def explain_inst(instruction):
    explanation = ""
    op_code = instruction[0:2]
    gd_wten = instruction[16]
    gd_rden = instruction[17]
    acc_en = instruction[18]
    addr_rd = instruction[19:27]
    addr_wt = instruction[28:36]
    oob_wtp = instruction[37:39]
    oob_rdp = instruction[40:42]

    if op_code == "000":
        explanation = explanation + "lis"
        fd_ar = instruction[3:11]
        pos = instruction[13:14]
    elif op_code == "001":
        explanation = explanation + "lisp"
        fd_ar = instruction[3:11]
        pos = instruction[13:14]
    elif op_code == "010":
        explanation = explanation + "wu"
        cm_ar = instruction[3:12]
        pos = instruction[13:14]
    elif op_code == "011":
        explanation = explanation + "wup"
        cm_ar = instruction[3:12]
        pos = instruction[13:14]
    elif op_code == "100":
        explanation = explanation + "cmpfis"
        fd_ar = instruction[3:11]
        ca = instruction[12:15]
    elif op_code == "101":
        explanation = explanation + "nop"
    elif op_code == "110":
        explanation = explanation + "cmpgt"
        ca = instruction[12:15]
    elif op_code == "111":
        explanation = explanation + "cmpgtp"
        ca = instruction[12:15]

    if gd_rden == 1 :
        explanation = explanation + "read_OS_addr " + addr_rd
    
    return explanation



# lis:
# lis + reg_position(0/1/2/3) + IS_addr(address 0-) + input_map_position

# input_map_position = i_input_channel * input_map_length + i_reg * BusWidth


# wu:
# wu + reg_position(0/1/2/3) + CIMaddress + weight_map_postion

# CIM address = i_pc * PC宽度 + i_reg * SCR宽度 + scr_num
# weight_map_position = i_channel + i_data


# cmpfis:
# cmpfis + IS_addr + ls + atos + OS_addr

# os_addr = i_input_channel * weight_channel + i_weight_channel

# 0:aor reg = reg + psum
# 1:tos OS = reg + psum, reg = 0
# 2:aos OS = psum + reg + OS, reg = 0


# 任务：
# 1 创建git repo
# 2 compiler生成机器码
# 3 reg的值改动为倒序
# 4 改wu load的长度bug